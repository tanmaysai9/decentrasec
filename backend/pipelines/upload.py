import base64
import io
import json
import mimetypes
import os
import time
from datetime import datetime, timezone
from uuid import uuid4

from PIL import Image

from config import NODE_NAMES, NODE_IPS, MAX_FILE_SIZE_MB, ENCRYPTED_DATA_DIR
from crypto.aes import generate_key, encrypt_stream
from crypto.hash import sha256_file, mock_merkle_root, mock_tx_hash
from crypto import dmaya as dmaya_mod
from ipfs.node import upload_to_node
from store import add_manifest

Image.MAX_IMAGE_PIXELS = None

_upload_status: dict = {}
_stage_timings: dict = {}

KEY_FILE = "key.bin"


def _classify(all_shares):
    essential = {}
    shares = []
    for rel_path in sorted(all_shares.keys()):
        fname = rel_path.rsplit("/", 1)[-1] if "/" in rel_path else rel_path
        data = all_shares[rel_path]
        if fname == "index.txt" or fname.endswith(".json") or fname.endswith(".txt"):
            essential[rel_path] = data
        else:
            shares.append((rel_path, data))
    return essential, shares


def _generate_thumbnail(file_path, file_name, size=256):
    try:
        ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
        if ext in ("tif", "tiff", "png", "jpg", "jpeg", "bmp", "webp", "gif"):
            img = Image.open(file_path)
            if img.mode not in ("RGB", "RGBA", "L"):
                img = img.convert("RGB")
        else:
            return None
        img.thumbnail((size, size))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return None


def get_upload_status(upload_id):
    return _upload_status.get(upload_id)


def _set_stage(upload_id, stage, stage_index, extra=None):
    now = time.monotonic()
    entry = _upload_status.get(upload_id, {})
    if upload_id in _stage_timings and _stage_timings[upload_id].get("_current"):
        prev = _stage_timings[upload_id].pop("_current")
        dur = round((now - prev["start"]) * 1000)
        _stage_timings[upload_id][prev["stage"]] = dur
    _stage_timings.setdefault(upload_id, {})[stage] = None
    _stage_timings[upload_id]["_current"] = {"stage": stage, "start": now}
    entry["stage"] = stage
    entry["stage_index"] = stage_index
    entry["stage_total"] = 5
    entry["stage_durations"] = {
        k: v for k, v in _stage_timings.get(upload_id, {}).items() if k != "_current"
    }
    if extra:
        entry.update(extra)
    _upload_status[upload_id] = entry


def _add_to_satellite_catalog(manifest, essential_b64, key_share_entries):
    try:
        from satellite.config import CATALOG_FILE

        catalog = None
        if CATALOG_FILE.exists():
            try:
                catalog = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
            except Exception:
                catalog = None
        if not catalog or "images" not in catalog:
            catalog = {"dataset": "User Uploads", "mode": "key", "total": 0, "images": []}

        essential_rel = ""
        essential_size = 0
        essential_hex = ""
        for rp, b64 in essential_b64.items():
            essential_rel = rp
            raw = base64.b64decode(b64)
            essential_size = len(raw)
            essential_hex = raw[:4].hex().upper()
            break

        img_entry = {
            "id": manifest["id"],
            "index": len(catalog["images"]),
            "lat": 0,
            "lon": 0,
            "season": "",
            "sensor": "UPLOAD",
            "resolution_m": 0,
            "acquisition_date": manifest.get("created_at", "")[:10],
            "cloud_cover": 0,
            "file_size": manifest["original_size"],
            "thumbnail": manifest.get("thumbnail", ""),
            "essential_share": {
                "index": 0,
                "hex_prefix": essential_hex,
                "rel_path": essential_rel,
                "node": "LOCAL",
                "node_ip": "",
                "cid": "",
                "size": essential_size,
                "thumbnail": "",
            },
            "shares": [
                {
                    "index": s["index"],
                    "node": s["node"],
                    "node_ip": s["node_ip"],
                    "rel_path": s["rel_path"],
                    "hex_prefix": s.get("hex_prefix", ""),
                    "cid": s["cid"],
                    "size": s["size"],
                    "thumbnail": "",
                }
                for s in key_share_entries
            ],
            "key_index": essential_b64,
            "blob_path": manifest["blob_path"],
            "encrypted_size": manifest["encrypted_size"],
            "aes_mode": manifest.get("aes_mode", "stream"),
            "nlss_ready": True,
            "ipfs_ready": True,
            "source": "upload",
            "file_name": manifest["file_name"],
        }

        catalog["images"].append(img_entry)
        catalog["total"] = len(catalog["images"])
        CATALOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CATALOG_FILE.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    except Exception as e:
        import logging
        logging.getLogger("upload").error("Catalog write failed: %s", e, exc_info=True)


async def run_upload(upload_id, file_path, file_name, owner_address):
    try:
        await _run_upload_inner(upload_id, file_path, file_name, owner_address)
    except Exception as e:
        entry = _upload_status.get(upload_id, {})
        entry["stage"] = "error"
        entry["error"] = str(e)
        _upload_status[upload_id] = entry
    finally:
        try:
            os.unlink(file_path)
        except Exception:
            pass


async def _run_upload_inner(upload_id, file_path, file_name, owner_address):
    t_start = time.monotonic()
    nodes = {n: {"cid": None, "status": "pending"} for n in NODE_NAMES}
    _set_stage(upload_id, "validate", 0, {"nodes": nodes})

    file_size = os.path.getsize(file_path)
    if file_size == 0:
        raise ValueError("Empty file.")
    if file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise ValueError(f"File exceeds {MAX_FILE_SIZE_MB}MB limit.")

    _set_stage(upload_id, "encrypt", 1, {"nodes": nodes})
    file_hash = sha256_file(file_path)
    thumbnail_b64 = _generate_thumbnail(file_path, file_name)

    key = generate_key()

    ENCRYPTED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    blob_path = ENCRYPTED_DATA_DIR / f"{upload_id}.bin"
    encrypt_stream(file_path, str(blob_path), key)
    encrypted_size = blob_path.stat().st_size

    _set_stage(upload_id, "split", 2, {"nodes": nodes})
    all_shares = dmaya_mod.encrypt(key, KEY_FILE)["shares"]
    essential_files, key_shares = _classify(all_shares)

    essential_b64 = {
        rp: base64.b64encode(d).decode("ascii")
        for rp, d in essential_files.items()
    }

    _set_stage(
        upload_id, "distribute", 3,
        {"nodes": nodes, "current_node": "", "nodes_completed": 0},
    )

    key_entries = []
    for idx, (rel_path, share_data) in enumerate(key_shares):
        node_name = NODE_NAMES[idx % len(NODE_NAMES)]
        nodes[node_name] = {"cid": None, "status": "uploading", "ip": NODE_IPS[node_name]}
        _set_stage(
            upload_id, "distribute", 3,
            {"nodes": dict(nodes), "current_node": node_name, "nodes_completed": idx},
        )
        safe_name = rel_path.replace("/", "_")
        cid = await upload_to_node(
            node_name, share_data, f"key_{safe_name}"
        )
        nodes[node_name] = {"cid": cid, "status": "ok"}
        key_entries.append({
            "index": idx,
            "node": node_name,
            "node_ip": NODE_IPS[node_name],
            "cid": cid,
            "rel_path": rel_path,
            "hex_prefix": share_data[:4].hex().upper(),
            "size": len(share_data),
        })
        _set_stage(
            upload_id, "distribute", 3,
            {"nodes": dict(nodes), "current_node": node_name, "nodes_completed": idx + 1},
        )

    _set_stage(upload_id, "anchor", 4, {"nodes": dict(nodes)})

    merkle = mock_merkle_root([e["cid"] for e in key_entries])
    tx = mock_tx_hash(upload_id)

    mime_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
    t_total = round((time.monotonic() - t_start) * 1000)
    stage_durations = {
        k: v for k, v in _stage_timings.get(upload_id, {}).items() if k != "_current"
    }

    manifest = {
        "id": upload_id,
        "owner_address": owner_address,
        "file_name": file_name,
        "original_size": file_size,
        "encrypted_size": encrypted_size,
        "mime_type": mime_type,
        "mode": "key",
        "aes_mode": "stream",
        "threshold_k": min(3, len(key_entries)),
        "total_shares_n": len(key_entries),
        "sha256": file_hash,
        "blob_path": str(blob_path),
        "essential_share": {
            "rel_path": list(essential_files.keys())[0] if essential_files else "",
            "hex_prefix": list(essential_files.values())[0][:4].hex().upper() if essential_files else "",
            "size": len(list(essential_files.values())[0]) if essential_files else 0,
        },
        "key_shares": key_entries,
        "key_index": essential_b64,
        "merkle_root": merkle,
        "tx_hash": tx,
        "thumbnail": thumbnail_b64,
        "upload_duration_ms": t_total,
        "stage_durations": stage_durations,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    add_manifest(manifest)
    _add_to_satellite_catalog(manifest, essential_b64, key_entries)

    _upload_status[upload_id] = {
        "stage": "done",
        "stage_index": 5,
        "stage_total": 5,
        "nodes": {
            n: {"cid": nodes[n].get("cid"), "status": nodes[n].get("status", "pending"), "ip": NODE_IPS[n]}
            for n in NODE_NAMES
        },
        "result": {"merkle_root": merkle, "tx_hash": tx},
        "upload_duration_ms": t_total,
        "stage_durations": stage_durations,
        "error": None,
    }
