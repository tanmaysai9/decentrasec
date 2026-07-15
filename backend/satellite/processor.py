import base64
import io
import json
import os
import tempfile
import time
import sys
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))

from satellite.config import CATALOG_FILE
from satellite import keymode

from ipfs.gateway import fetch_bytes
from ipfs.node import fetch_from_node


def get_catalog():
    if not CATALOG_FILE.exists():
        return None
    return json.loads(CATALOG_FILE.read_text(encoding="utf-8"))


async def reconstruct_image(img_id):
    catalog = get_catalog()
    if not catalog:
        raise ValueError("Catalog not found. Run setup first.")

    entry = None
    for img in catalog["images"]:
        if img["id"] == img_id:
            entry = img
            break
    if not entry:
        raise ValueError(f"Image '{img_id}' not found in catalog")

    t0 = time.monotonic()

    blob_path = Path(entry["blob_path"])
    if not blob_path.exists():
        raise ValueError(f"Ciphertext blob not found: {blob_path}")
    aes_mode = entry.get("aes_mode", "gcm")
    if aes_mode != "stream":
        blob = blob_path.read_bytes()
    t_blob = round((time.monotonic() - t0) * 1000)

    essential_files = {
        rel: base64.b64decode(b) for rel, b in entry.get("key_index", {}).items()
    }

    t1 = time.monotonic()
    key_shares_fetched = {}
    for s in entry.get("shares", []):
        cid = s["cid"]
        node_name = s.get("node")
        try:
            if node_name and node_name != "LOCAL":
                data = await fetch_from_node(node_name, cid)
            else:
                data = await fetch_bytes(cid)
        except Exception:
            data = await fetch_bytes(cid)
        key_shares_fetched[s["rel_path"]] = data
    t_ipfs_get = round((time.monotonic() - t1) * 1000)

    t2 = time.monotonic()
    if aes_mode == "stream":
        tmp_path = tempfile.mktemp(suffix="_sat_dec")
        keymode.decrypt_image_stream(
            str(blob_path), tmp_path, essential_files, key_shares_fetched
        )
        t_decrypt = round((time.monotonic() - t2) * 1000)

        duration_ms = round((time.monotonic() - t0) * 1000)
        n_ipfs = len(entry.get("shares", []))

        return {
            "data_path": tmp_path,
            "file_name": f"{img_id}.tif",
            "mime_type": "image/tiff",
            "shares_used": f"{n_ipfs}/{n_ipfs}",
            "reconstruct_duration_ms": duration_ms,
            "metrics": {
                "read_blob_ms": t_blob,
                "ipfs_get_ms": t_ipfs_get,
                "decrypt_ms": t_decrypt,
                "total_ms": duration_ms,
            },
            "essential_share": entry.get("essential_share", {}),
            "shares": entry.get("shares", []),
            "image": entry,
        }
    else:
        blob = blob_path.read_bytes()
        raw_bytes = keymode.decrypt_image(blob, essential_files, key_shares_fetched)
        t_decrypt = round((time.monotonic() - t2) * 1000)

        duration_ms = round((time.monotonic() - t0) * 1000)
        n_ipfs = len(entry.get("shares", []))

        return {
            "data": raw_bytes,
            "file_name": f"{img_id}.tif",
            "mime_type": "image/tiff",
            "shares_used": f"{n_ipfs}/{n_ipfs}",
            "reconstruct_duration_ms": duration_ms,
            "metrics": {
                "read_blob_ms": t_blob,
                "ipfs_get_ms": t_ipfs_get,
                "decrypt_ms": t_decrypt,
                "total_ms": duration_ms,
            },
            "essential_share": entry.get("essential_share", {}),
            "shares": entry.get("shares", []),
            "image": entry,
        }
