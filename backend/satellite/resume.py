import asyncio
import json
import sys
from pathlib import Path

import httpx
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))

from satellite.config import (
    RAW_DIR, CATALOG_FILE,
    SENSORS, SEASONS, RESOLUTIONS,
    NODE_NAMES, STAC_URL, STAC_REGIONS, STAC_PAGE_SIZE,
)
from satellite.setup import _process_image, _discover_items


async def resume(start_idx=32):
    if not CATALOG_FILE.exists():
        print("  ERROR: No catalog found. Run rebuild/setup first.")
        return

    catalog = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    existing_count = len(catalog["images"])

    print("=" * 60)
    print(f"  Resume (Key Mode) — downloading more scenes")
    print(f"  Existing in catalog: {existing_count}")
    print("=" * 60)

    print(f"\n  [1/2] Discovering scenes from STAC API (offset {start_idx})...")
    with httpx.Client(timeout=30) as client:
        items = _discover_items(client)[start_idx:]
    needed = 100 - existing_count
    items = items[:needed]
    print(f"       Found {len(items)} new scenes to download.")

    if not items:
        print("  Nothing to download.")
        return

    Image.MAX_IMAGE_PIXELS = None
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n  [2/2] Processing {len(items)} images...")
    new_images = []

    for j, item in enumerate(items):
        i = existing_count + j
        img_id = f"img_{i:03d}"

        print(f"\n  [{j+1}/{len(items)}] {img_id} ({item['sensor']}, {item['season']})")
        print(f"    Downloading from STAC...", end=" ", flush=True)

        try:
            with httpx.Client(timeout=120, follow_redirects=True) as client:
                resp = client.get(item["tiff_url"], timeout=120)
                resp.raise_for_status()
                raw_bytes = resp.content
        except Exception as e:
            print(f"FAILED: {e}")
            continue

        print(f"{len(raw_bytes) / 1024 / 1024:.1f} MB")
        print(f"    AES encrypt + NLSS key split...", end=" ", flush=True)
        try:
            proc = await _process_image(img_id, item, raw_bytes)
        except Exception as e:
            print(f"FAILED: {e}")
            continue
        print("OK")

        new_images.append({
            "id": img_id,
            "index": i,
            "lat": item["lat"],
            "lon": item["lon"],
            "season": item["season"],
            "sensor": item["sensor"],
            "resolution_m": item["resolution_m"],
            "acquisition_date": item["acquisition_date"],
            "cloud_cover": item.get("cloud_cover", 0),
            "file_size": len(raw_bytes),
            **proc,
            "nlss_ready": True,
            "ipfs_ready": True,
        })

    catalog["images"].extend(new_images)
    catalog["total"] = len(catalog["images"])
    CATALOG_FILE.write_text(json.dumps(catalog, indent=2), encoding="utf-8")

    print(f"\n{'=' * 60}")
    print(f"  Resume complete!")
    print(f"  New images:    {len(new_images)}")
    print(f"  Total catalog: {catalog['total']}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=32)
    args = parser.parse_args()
    asyncio.run(resume(start_idx=args.start))
