import base64
import time
from pathlib import Path

from crypto.aes import decrypt as aes_decrypt
from crypto.hash import sha256
from crypto import dmaya as dmaya_mod
from ipfs.gateway import fetch_bytes
from ipfs.node import fetch_from_node
from store import get_manifest

KEY_FILE = "key.bin"


async def _fetch_share(entry):
    node_name = entry.get("node")
    if node_name:
        try:
            return await fetch_from_node(node_name, entry["cid"])
        except Exception:
            pass
    return await fetch_bytes(entry["cid"])


async def reconstruct_by_id(manifest_id):
    manifest = get_manifest(manifest_id)
    if not manifest:
        raise ValueError("Manifest not found")
    return await _reconstruct(manifest)


async def _reconstruct(manifest):
    t_start = time.monotonic()

    all_shares = {}

    essential_b64 = manifest.get("key_index", {})
    for rel_path, b64_data in essential_b64.items():
        all_shares[rel_path] = base64.b64decode(b64_data)

    for entry in manifest["key_shares"]:
        data = await _fetch_share(entry)
        all_shares[entry["rel_path"]] = data

    if not all_shares:
        raise ValueError("No shares found in manifest")

    key = dmaya_mod.decrypt(all_shares, KEY_FILE)

    if len(key) == 0:
        raise ValueError(
            f"Key reconstruction returned 0 bytes. "
            f"Shares available: {len(all_shares)}. "
            f"Check DMaya binary and mono runtime."
        )

    blob_path = Path(manifest["blob_path"])
    if not blob_path.exists():
        raise ValueError(f"Ciphertext blob not found: {blob_path}")
    blob = blob_path.read_bytes()

    plaintext = aes_decrypt(blob, key)

    actual_hash = sha256(plaintext)
    expected_hash = manifest["sha256"]
    if actual_hash != expected_hash:
        raise ValueError(
            f"Integrity check failed: expected {expected_hash}, got {actual_hash}"
        )

    shares_used = f"{manifest.get('threshold_k', '?')}/{manifest.get('total_shares_n', '?')}"
    duration_ms = round((time.monotonic() - t_start) * 1000)

    return {
        "data": plaintext,
        "file_name": manifest["file_name"],
        "mime_type": manifest["mime_type"],
        "merkle_root": manifest.get("merkle_root", ""),
        "shares_used": shares_used,
        "reconstruct_duration_ms": duration_ms,
    }
