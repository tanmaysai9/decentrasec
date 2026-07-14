import base64
import io
import json
import mimetypes
import time
from datetime import datetime, timezone
from uuid import uuid4

from PIL import Image

from config import NODE_NAMES, NODE_IPS, MAX_FILE_SIZE_MB, ENCRYPTED_DATA_DIR
from crypto.aes import generate_key, encrypt as aes_encrypt
from crypto.hash import sha256, mock_merkle_root, mock_tx_hash
from crypto import dmaya as dmaya_mod
from ipfs.node import upload_to_node
from store import add_manifest

Image.MAX_IMAGE_PIXELS = None

_upload_status: dict = {}
_stage_timings: dict = {}

KEY_FILE = "key.bin"


def _generate_thumbnail(file_bytes, file_name, size=256):
    try:
        ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
        if ext in ("tif", "tiff", "png", "jpg", "jpeg", "bmp", "webp", "gif"):
            img = Image.open(io.BytesIO(file_bytes))
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


def _add_to_satellite_catalog(manifest, all_shares_meta):
    try:
        from satellite.config import CATALOG_FILE

        if CATALOG_FILE.exists():
            catalog = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
        else:
            catalog = {"dataset": "User Uploads", "mode": "key", "total": 0, "images": []}

        essential_meta = all_shares_meta[0] if all_shares_meta else {}
        key_share_metas = all_shares_meta[1:] if len(all_shares_meta) > 1 else []

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
                "hex_prefix": essential_meta.get("hex_prefix", ""),
                "rel_path": essential_meta.get("rel_path", ""),
                "node": essential_meta.get("node", ""),
                "node_ip": essential_meta.get("node_ip", ""),
                "cid": essential_meta.get("cid", ""),
                "size": essential_meta.get("size", 0),
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
                for s in key_share_metas
            ],
            "blob_path": manifest["blob_path"],
            "encrypted_size": manifest["encrypted_size"],
            "nlss_ready": True,
            "ipfs_ready": True,
            "source": "upload",
            "file_name": manifest["file_name"],
        }

        catalog["images"].append(img_entry)
        catalog["total"] = len(catalog["images"])
        CATALOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CATALOG_FILE.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    except Exception:
        pass


async def run_upload(upload_id, file_bytes, file_name, owner_address):
    try:
        await _run_upload_inner(upload_id, file_bytes, file_name, owner_address)
    except Exception as e:
        entry = _upload_status.get(upload_id, {})
        entry["stage"] = "error"
        entry["error"] = str(e)
        _upload_status[upload_id] = entry


async def _run_upload_inner(upload_id, file_bytes, file_name, owner_address):
    t_start = time.monotonic()
    nodes = {n: {"cid": None, "status": "pending"} for n in NODE_NAMES}
    _set_stage(upload_id, "validate", 0, {"nodes": nodes})

    if len(file_bytes) == 0:
        raise ValueError("Empty file.")
    if len(file_bytes) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise ValueError(f"File exceeds {MAX_FILE_SIZE_MB}MB limit.")

    _set_stage(upload_id, "encrypt", 1, {"nodes": nodes})
    file_hash = sha256(file_bytes)
    thumbnail_b64 = _generate_thumbnail(file_bytes, file_name)

    key = generate_key()
    blob = aes_encrypt(file_bytes, key)

    ENCRYPTED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    blob_path = ENCRYPTED_DATA_DIR / f"{upload_id}.bin"
    blob_path.write_bytes(blob)

    _set_stage(upload_id, "split", 2, {"nodes": nodes})
    all_shares = dmaya_mod.encrypt(key, KEY_FILE)["shares"]
    sorted_shares = sorted(all_shares.items())

    _set_stage(
        upload_id, "distribute", 3,
        {"nodes": nodes, "current_node": "", "nodes_completed": 0},
    )

    share_entries = []
    for idx, (rel_path, share_data) in enumerate(sorted_shares):
        node_name = NODE_NAMES[idx % len(NODE_NAMES)]
        nodes[node_name] = {"cid": None, "status": "uploading", "ip": NODE_IPS[node_name]}
        _set_stage(
            upload_id, "distribute", 3,
            {"nodes": dict(nodes), "current_node": node_name, "nodes_completed": idx},
        )
        cid = await upload_to_node(
            node_name, share_data, f"key_{rel_path}"
        )
        nodes[node_name] = {"cid": cid, "status": "ok"}
        share_entries.append({
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

    merkle = mock_merkle_root([e["cid"] for e in share_entries])
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
        "original_size": len(file_bytes),
        "encrypted_size": len(blob),
        "mime_type": mime_type,
        "mode": "key",
        "threshold_k": min(3, len(share_entries)),
        "total_shares_n": len(share_entries),
        "sha256": file_hash,
        "blob_path": str(blob_path),
        "key_shares": share_entries,
        "merkle_root": merkle,
        "tx_hash": tx,
        "thumbnail": thumbnail_b64,
        "upload_duration_ms": t_total,
        "stage_durations": stage_durations,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    add_manifest(manifest)
    _add_to_satellite_catalog(manifest, share_entries)

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
