import gzip
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


def _classify(all_shares):
    index_files = {}
    shares = []
    for rel_path in sorted(all_shares.keys()):
        fname = rel_path.rsplit("/", 1)[-1] if "/" in rel_path else rel_path
        data = all_shares[rel_path]
        if fname == "index.txt" or fname.endswith(".json") or fname.endswith(".txt"):
            index_files[rel_path] = data
        else:
            shares.append((rel_path, data))
    return index_files, shares


def _generate_thumbnail(file_bytes, file_name, size=128):
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
        img.save(buf, format="JPEG", quality=60)
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
    entry["stage_total"] = 6
    entry["stage_durations"] = {
        k: v for k, v in _stage_timings.get(upload_id, {}).items() if k != "_current"
    }
    if extra:
        entry.update(extra)
    _upload_status[upload_id] = entry


def _add_to_satellite_catalog(manifest, key_index_b64):
    try:
        from satellite.config import CATALOG_FILE
        import math

        if CATALOG_FILE.exists():
            catalog = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
        else:
            catalog = {"dataset": "User Uploads", "mode": "key", "total": 0, "images": []}

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
                "hex_prefix": manifest.get("blob_hex_prefix", ""),
                "rel_path": f'{manifest["id"]}.bin',
                "share_file": manifest["blob_path"],
                "size": manifest["encrypted_size"],
                "thumbnail": "",
            },
            "shares": [
                {
                    "index": ks["index"],
                    "node": ks["node"],
                    "node_ip": ks["node_ip"],
                    "rel_path": ks["rel_path"],
                    "hex_prefix": ks.get("hex_prefix", ""),
                    "cid": ks["cid"],
                    "size": ks["size"],
                    "thumbnail": "",
                }
                for ks in manifest["key_shares"]
            ],
            "key_index": key_index_b64,
            "blob_path": manifest["blob_path"],
            "compressed_size": manifest["compressed_size"],
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

    _set_stage(upload_id, "compress", 1, {"nodes": nodes})
    compressed = gzip.compress(file_bytes, compresslevel=6)
    file_hash = sha256(file_bytes)
    thumbnail_b64 = _generate_thumbnail(file_bytes, file_name)

    _set_stage(upload_id, "encrypt", 2, {"nodes": nodes})
    key = generate_key()
    blob = aes_encrypt(compressed, key)

    ENCRYPTED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    blob_path = ENCRYPTED_DATA_DIR / f"{upload_id}.bin"
    blob_path.write_bytes(blob)

    _set_stage(upload_id, "split", 3, {"nodes": nodes})
    all_shares = dmaya_mod.encrypt(key, KEY_FILE)["shares"]
    index_files, key_shares = _classify(all_shares)

    _set_stage(
        upload_id, "distribute", 4,
        {"nodes": nodes, "current_node": "", "nodes_completed": 0},
    )

    key_entries = []
    for idx, (rel_path, share_data) in enumerate(key_shares):
        node_name = NODE_NAMES[idx % len(NODE_NAMES)]
        nodes[node_name] = {"cid": None, "status": "uploading", "ip": NODE_IPS[node_name]}
        _set_stage(
            upload_id, "distribute", 4,
            {"nodes": dict(nodes), "current_node": node_name, "nodes_completed": idx},
        )
        cid = await upload_to_node(
            node_name, share_data, f"key_{rel_path}"
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
            upload_id, "distribute", 4,
            {"nodes": dict(nodes), "current_node": node_name, "nodes_completed": idx + 1},
        )

    _set_stage(upload_id, "anchor", 5, {"nodes": dict(nodes)})

    merkle = mock_merkle_root([e["cid"] for e in key_entries])
    tx = mock_tx_hash(upload_id)

    key_index_b64 = {
        rel: base64.b64encode(data).decode("ascii")
        for rel, data in index_files.items()
    }

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
        "compressed_size": len(compressed),
        "encrypted_size": len(blob),
        "blob_hex_prefix": blob[:4].hex().upper(),
        "mime_type": mime_type,
        "mode": "key",
        "threshold_k": min(3, len(key_entries)),
        "total_shares_n": len(key_entries),
        "sha256": file_hash,
        "blob_path": str(blob_path),
        "key_shares": key_entries,
        "key_index": key_index_b64,
        "merkle_root": merkle,
        "tx_hash": tx,
        "thumbnail": thumbnail_b64,
        "upload_duration_ms": t_total,
        "stage_durations": stage_durations,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    add_manifest(manifest)
    _add_to_satellite_catalog(manifest, key_index_b64)

    _upload_status[upload_id] = {
        "stage": "done",
        "stage_index": 6,
        "stage_total": 6,
        "nodes": {
            n: {"cid": nodes[n]["cid"], "status": "ok", "ip": NODE_IPS[n]}
            for n in NODE_NAMES
        },
        "result": {"merkle_root": merkle, "tx_hash": tx},
        "upload_duration_ms": t_total,
        "stage_durations": stage_durations,
        "error": None,
    }
