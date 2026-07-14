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

_upload_status: dict = {}
_stage_timings: dict = {}

DMAYA_KEY_FILE = "key.bin"


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
    aes_key = generate_key()
    blob = aes_encrypt(compressed, aes_key)

    ENCRYPTED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    blob_path = ENCRYPTED_DATA_DIR / f"{upload_id}.bin"
    blob_path.write_bytes(blob)

    _set_stage(upload_id, "split", 3, {"nodes": nodes})
    key_shares = dmaya_mod.encrypt(aes_key, DMAYA_KEY_FILE)["shares"]

    _set_stage(
        upload_id, "distribute", 4,
        {"nodes": nodes, "current_node": "", "nodes_completed": 0},
    )

    key_entries = []
    for idx, rel_path in enumerate(sorted(key_shares.keys())):
        node_name = NODE_NAMES[idx % len(NODE_NAMES)]
        nodes[node_name] = {"cid": None, "status": "uploading", "ip": NODE_IPS[node_name]}
        _set_stage(
            upload_id, "distribute", 4,
            {"nodes": dict(nodes), "current_node": node_name, "nodes_completed": idx},
        )
        cid = await upload_to_node(
            node_name, key_shares[rel_path], f"key_{rel_path}"
        )
        nodes[node_name] = {"cid": cid, "status": "ok"}
        key_entries.append({
            "index": idx,
            "node": node_name,
            "node_ip": NODE_IPS[node_name],
            "cid": cid,
            "rel_path": rel_path,
            "size": len(key_shares[rel_path]),
        })
        _set_stage(
            upload_id, "distribute", 4,
            {"nodes": dict(nodes), "current_node": node_name, "nodes_completed": idx + 1},
        )

    _set_stage(upload_id, "anchor", 5, {"nodes": dict(nodes)})

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
        "original_size": len(file_bytes),
        "compressed_size": len(compressed),
        "encrypted_size": len(blob),
        "mime_type": mime_type,
        "scheme": "DMAYA-KEY",
        "mode": "key",
        "threshold_k": 3,
        "total_shares_n": len(key_entries),
        "sha256": file_hash,
        "blob_path": str(blob_path),
        "key_shares": key_entries,
        "merkle_root": merkle,
        "tx_hash": tx,
        "thumbnail": thumbnail_b64,
        "upload_duration_ms": t_total,
        "stage_durations": stage_durations,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    add_manifest(manifest)

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
