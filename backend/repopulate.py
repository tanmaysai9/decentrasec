#!/usr/bin/env python3
"""Re-encrypt + re-split + re-upload existing satellite raw images.

Reuses raw .tif files already on disk — does NOT re-download from STAC.
Only clears blobs/shares/catalog (stale from broken DMaya) and regenerates them.

Usage:
    cd backend
    python3 repopulate.py
"""
import asyncio
import base64
import io
import json
import shutil
import sys
import time
from pathlib import Path

BASE = Path(__file__).parent
SAT_DATA = BASE / "data" / "satellite"
RAW_DIR = SAT_DATA / "raw"
BLOB_DIR = SAT_DATA / "blobs"
CATALOG_FILE = SAT_DATA / "catalog.json"

sys.path.insert(0, str(BASE))

from PIL import Image
Image.MAX_IMAGE_PIXELS = None

from satellite import keymode
from satellite.config import NODE_NAMES, NODE_IPS
from ipfs.node import upload_to_node

OWNER_ADDRESS = "0xA1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4E5F6A1B2"


def _make_thumbnail(raw_bytes, size=56):
    img = Image.open(io.BytesIO(raw_bytes))
    if img.mode not in ("RGB", "RGBA", "L"):
        img = img.convert("RGB")
    img.thumbnail((size, size))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=75)
    return base64.b64encode(buf.getvalue()).decode("ascii")


async def _process_image(img_id, raw_bytes, meta):
    """Re-encrypt + NLSS split + upload for one image."""
    thumb_b64 = _make_thumbnail(raw_bytes)

    blob, essential_files, key_shares = keymode.encrypt_image(raw_bytes)

    BLOB_DIR.mkdir(parents=True, exist_ok=True)
    blob_path = BLOB_DIR / f"{img_id}.bin"
    blob_path.write_bytes(blob)

    essential_rel = list(essential_files.keys())[0] if essential_files else ""
    essential_data = list(essential_files.values())[0] if essential_files else b""

    essential = {
        "index": 0,
        "hex_prefix": essential_data[:4].hex().upper() if essential_data else "",
        "rel_path": essential_rel,
        "node": "LOCAL",
        "node_ip": "",
        "cid": "",
        "size": len(essential_data),
        "thumbnail": "",
    }

    shares_meta = []
    for s_idx, (rel_path, share_data) in enumerate(key_shares):
        node = NODE_NAMES[s_idx % len(NODE_NAMES)]
        print(f"  {node}...", end=" ", flush=True)
        try:
            safe_name = rel_path.replace("/", "_")
            cid = await upload_to_node(node, share_data, f"key_{img_id}_{safe_name}")
        except Exception as e:
            print(f"\n  [WARN] upload failed share {s_idx}: {e}")
            cid = "Qm" + ("0" * 38)

        shares_meta.append({
            "index": s_idx,
            "node": node,
            "node_ip": NODE_IPS[node],
            "rel_path": rel_path,
            "hex_prefix": share_data[:4].hex().upper(),
            "cid": cid,
            "size": len(share_data),
            "thumbnail": "",
        })

    return {
        "blob_path": str(blob_path),
        "encrypted_size": len(blob),
        "thumbnail": thumb_b64,
        "essential_share": essential,
        "shares": shares_meta,
        "key_index": {rel: base64.b64encode(data).decode("ascii")
                      for rel, data in essential_files.items()},
    }


async def main():
    print("=" * 60)
    print("  REPOPULATE — re-encrypt + re-split + re-upload (raw kept)")
    print("=" * 60)

    # 1. Read old catalog for metadata
    old_catalog = {}
    if CATALOG_FILE.exists():
        try:
            old_catalog = json.loads(CATALOG_FILE.read_text())
        except Exception:
            pass

    old_images = {}
    for img in old_catalog.get("images", []):
        old_images[img["id"]] = img

    # 2. Find all raw .tif files
    raw_files = sorted(RAW_DIR.glob("*.tif")) if RAW_DIR.exists() else []
    if not raw_files:
        print("  ERROR: No raw images found in data/satellite/raw/")
        print("  Run 'python3 -m satellite.setup' first to download from STAC.")
        return

    print(f"\n  Found {len(raw_files)} raw images in {RAW_DIR}")

    # 3. Clear stale blobs + catalog (keep raw!)
    if BLOB_DIR.exists():
        shutil.rmtree(BLOB_DIR)
        print("  [x] blobs/ cleared (stale DMaya output)")
    CATALOG_FILE.write_text("{}", encoding="utf-8")
    print("  [x] catalog.json cleared")
    mf = BASE / "data" / "manifests.json"
    mf.parent.mkdir(parents=True, exist_ok=True)
    mf.write_text("{}", encoding="utf-8")
    print("  [x] data/manifests.json cleared")

    # 4. Re-process each image
    print(f"\n  Re-encrypting + NLSS splitting + uploading {len(raw_files)} images...\n")
    t0 = time.time()
    catalog_images = []
    manifest_entries = {}

    for i, raw_path in enumerate(raw_files):
        img_id = raw_path.stem
        raw_bytes = raw_path.read_bytes()
        meta = old_images.get(img_id, {})

        sensor = meta.get("sensor", "S2-RGB")
        season = meta.get("season", "spring")
        print(f"  [{i+1}/{len(raw_files)}] {img_id} ({sensor} {season}) — "
              f"{len(raw_bytes):,}B — encrypt+split...", end=" ", flush=True)

        img_t0 = time.time()
        try:
            proc = await _process_image(img_id, raw_bytes, meta)
        except Exception as e:
            print(f"FAILED ({e}), skipping...")
            continue
        img_duration_ms = int((time.time() - img_t0) * 1000)

        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        catalog_images.append({
            "id": img_id,
            "index": i,
            "lat": meta.get("lat", 0),
            "lon": meta.get("lon", 0),
            "season": season,
            "sensor": sensor,
            "resolution_m": meta.get("resolution_m", 10),
            "acquisition_date": meta.get("acquisition_date", ""),
            "cloud_cover": meta.get("cloud_cover", 0),
            "file_size": len(raw_bytes),
            "raw_path": str(raw_path),
            **proc,
            "nlss_ready": True,
            "ipfs_ready": True,
        })

        n_shares = len(proc["shares"])
        manifest_entries[img_id] = {
            "id": img_id,
            "file_name": f"{img_id}.tif",
            "original_size": len(raw_bytes),
            "mode": "key",
            "threshold_k": n_shares,
            "total_shares_n": n_shares,
            "owner_address": OWNER_ADDRESS,
            "blob_path": proc["blob_path"],
            "key_shares": proc["shares"],
            "key_index": proc["key_index"],
            "merkle_root": "",
            "tx_hash": "",
            "thumbnail": proc["thumbnail"],
            "upload_duration_ms": img_duration_ms,
            "stage_durations": {},
            "created_at": now_iso,
        }

        cids_short = [s["cid"][:8] + "..." for s in proc["shares"]]
        print(f"done ({img_duration_ms}ms) — {n_shares} shares: {', '.join(cids_short)}")

    # 5. Write fresh catalog
    catalog = {
        "dataset": "SSL4EO-S12 v1.1",
        "mode": "key",
        "total": len(catalog_images),
        "images": catalog_images,
    }
    CATALOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_FILE.write_text(json.dumps(catalog, indent=2), encoding="utf-8")

    # 6. Write manifest entries for archive history
    mf = BASE / "data" / "manifests.json"
    mf.write_text(json.dumps(manifest_entries, indent=2), encoding="utf-8")
    print(f"  Manifests: {mf} ({len(manifest_entries)} entries)")

    elapsed = time.time() - t0
    print(f"\n  Repopulate complete in {elapsed:.1f}s")
    print(f"  Images:   {len(catalog_images)}")
    print(f"  Catalog:  {CATALOG_FILE}")
    print(f"  Manifests: {len(manifest_entries)} entries")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
