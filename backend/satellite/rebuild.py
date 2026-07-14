import asyncio
import json
import sys
import time
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))

from satellite.config import (
    RAW_DIR, CATALOG_FILE,
    SENSORS, SEASONS, RESOLUTIONS,
)
from satellite.setup import _process_image


def _guess_metadata(idx):
    sensor = SENSORS[idx % len(SENSORS)]
    season = SEASONS[(idx // len(SENSORS)) % len(SEASONS)]
    return {
        "sensor": sensor,
        "season": season,
        "lat": 0.0,
        "lon": 0.0,
        "acquisition_date": "2023-01-01",
        "cloud_cover": 0,
        "resolution_m": RESOLUTIONS.get(sensor, 10),
    }


async def rebuild():
    raw_files = sorted(RAW_DIR.glob("img_*.tif"))
    if not raw_files:
        print("  No raw images found in", RAW_DIR)
        return

    print("=" * 60)
    print(f"  Clean Rebuild (Key Mode) — {len(raw_files)} images")
    print(f"  Ciphertext: LOCAL | NLSS key shares: IPFS")
    print("=" * 60)

    Image.MAX_IMAGE_PIXELS = None
    catalog_images = []

    for i, raw_path in enumerate(raw_files):
        img_id = raw_path.stem
        idx = int(img_id.split("_")[1])
        meta = _guess_metadata(idx)

        print(f"\n  [{i+1}/{len(raw_files)}] {img_id} ({meta['sensor']}, {meta['season']})")
        print(f"    Raw: {raw_path.stat().st_size / 1024 / 1024:.1f} MB")

        raw_bytes = raw_path.read_bytes()
        print(f"    AES encrypt + NLSS key split...", end=" ", flush=True)
        try:
            proc = await _process_image(img_id, None, raw_bytes)
        except Exception as e:
            print(f"FAILED: {e}")
            continue
        print("OK")

        catalog_images.append({
            "id": img_id,
            "index": idx,
            "lat": meta["lat"],
            "lon": meta["lon"],
            "season": meta["season"],
            "sensor": meta["sensor"],
            "resolution_m": meta["resolution_m"],
            "acquisition_date": meta["acquisition_date"],
            "cloud_cover": meta.get("cloud_cover", 0),
            "file_size": len(raw_bytes),
            **proc,
            "nlss_ready": True,
            "ipfs_ready": True,
        })

    catalog = {
        "dataset": "SSL4EO-S12 v1.1",
        "mode": "key",
        "total": len(catalog_images),
        "images": catalog_images,
    }
    CATALOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_FILE.write_text(json.dumps(catalog, indent=2), encoding="utf-8")

    print(f"\n{'=' * 60}")
    print(f"  Rebuild complete!")
    print(f"  Images:   {len(catalog_images)}")
    print(f"  Catalog:  {CATALOG_FILE}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(rebuild())
