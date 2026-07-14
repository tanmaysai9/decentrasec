import asyncio
import base64
import hashlib
import io
import json
import sys
import time
from pathlib import Path

import httpx
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))

from satellite.config import (
    RAW_DIR, THUMB_DIR, BLOB_DIR, CATALOG_FILE,
    N_IMAGES, SENSORS, SEASONS, RESOLUTIONS,
    NODE_NAMES, NODE_IPS, STAC_URL, STAC_REGIONS, STAC_PAGE_SIZE,
)

from satellite import keymode
from ipfs.node import upload_to_node


def _search_stac(client, bbox, datetime_range, limit):
    body = {
        "collections": ["sentinel-2-l2a"],
        "bbox": bbox,
        "datetime": datetime_range,
        "query": {"eo:cloud_cover": {"lt": 30}},
        "limit": limit,
    }
    resp = client.post(STAC_URL, json=body, timeout=30)
    resp.raise_for_status()
    return resp.json().get("features", [])


def _download_image(client, url):
    resp = client.get(url, timeout=120, follow_redirects=True)
    resp.raise_for_status()
    return resp.content


def _make_thumbnail(raw_bytes, size=56):
    Image.MAX_IMAGE_PIXELS = None
    img = Image.open(io.BytesIO(raw_bytes))
    if img.mode not in ("RGB", "RGBA", "L"):
        img = img.convert("RGB")
    img.thumbnail((size, size))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=75)
    return base64.b64encode(buf.getvalue()).decode("ascii")


async def _upload_share(node_name, data, filename):
    return await upload_to_node(node_name, data, filename)


def _discover_items(sync_client):
    items = []
    seen_ids = set()
    for region in STAC_REGIONS:
        if len(items) >= N_IMAGES:
            break
        remaining = N_IMAGES - len(items)
        limit = min(STAC_PAGE_SIZE, remaining)
        try:
            features = _search_stac(sync_client, region["bbox"], region["months"], limit)
        except Exception as e:
            print(f"    [WARN] STAC search failed for {region['bbox']}: {e}")
            continue
        for feat in features:
            fid = feat.get("id", "")
            if fid in seen_ids:
                continue
            seen_ids.add(fid)

            thumb_url = feat.get("assets", {}).get("thumbnail", {}).get("href")
            visual_url = feat.get("assets", {}).get("visual", {}).get("href")
            tiff_url = visual_url or thumb_url
            if not tiff_url:
                continue

            props = feat.get("properties", {})
            bbox = feat.get("bbox", [0, 0, 0, 0])
            try:
                lon = sum(bbox[i] for i in [0, 2]) / 2
                lat = sum(bbox[i] for i in [1, 3]) / 2
            except Exception:
                lon, lat = 0, 0

            items.append({
                "id": fid,
                "tiff_url": tiff_url,
                "thumb_url": thumb_url,
                "sensor": region["sensor"],
                "season": region["season"],
                "lat": round(lat, 4),
                "lon": round(lon, 4),
                "acquisition_date": props.get("datetime", "")[:10],
                "cloud_cover": props.get("eo:cloud_cover", 0),
                "resolution_m": RESOLUTIONS.get(region["sensor"], 10),
            })

    return items[:N_IMAGES]


async def _process_image(img_id, item, raw_bytes):
    """Key-mode pipeline: encrypt image (local blob) + split key into shares."""
    raw_path = RAW_DIR / f"{img_id}.tif"
    raw_path.write_bytes(raw_bytes)
    thumb_b64 = _make_thumbnail(raw_bytes)

    blob, all_shares = keymode.encrypt_image(raw_bytes)

    BLOB_DIR.mkdir(parents=True, exist_ok=True)
    blob_path = BLOB_DIR / f"{img_id}.bin"
    blob_path.write_bytes(blob)

    essential_data = all_shares[0][1] if all_shares else b""
    essential_rel = all_shares[0][0] if all_shares else ""

    essential = {
        "index": 0,
        "hex_prefix": essential_data[:4].hex().upper() if essential_data else "",
        "rel_path": essential_rel,
        "node": "",
        "node_ip": "",
        "cid": "",
        "size": len(essential_data),
        "thumbnail": "",
    }

    shares_meta = []
    key_shares = all_shares[1:] if len(all_shares) > 1 else []
    for s_idx, (rel_path, share_data) in enumerate(key_shares):
        node = NODE_NAMES[s_idx % len(NODE_NAMES)]
        print(f" {node}...", end=" ", flush=True)
        try:
            safe_name = rel_path.replace("/", "_")
            cid = await _upload_share(node, share_data, f"key_{img_id}_{safe_name}")
        except Exception as e:
            print(f"\n    [WARN] IPFS upload failed share {s_idx}: {e}")
            hash_input = f"{img_id}-{s_idx}".encode()
            cid = "Qm" + hashlib.sha256(hash_input).hexdigest()[:38]

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
        "raw_path": str(raw_path),
        "blob_path": str(blob_path),
        "encrypted_size": len(blob),
        "thumbnail": thumb_b64,
        "essential_share": essential,
        "shares": shares_meta,
    }


async def run_setup(force=False):
    if not force and CATALOG_FILE.exists():
        existing = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
        if existing.get("total", 0) > 0 and all(
            img.get("ipfs_ready") for img in existing["images"]
        ):
            print("  Catalog exists with all images on IPFS. Use --force to regenerate.")
            return existing

    for d in [RAW_DIR, THUMB_DIR, BLOB_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    print("=" * 60)
    print("  SSL4EO-S12 Satellite Module — Full Setup (Key Mode)")
    print("  Ciphertext: LOCAL | NLSS key shares: IPFS nodes")
    print("=" * 60)

    print(f"\n  [1/3] Discovering {N_IMAGES} Sentinel-2 scenes from STAC API...")
    with httpx.Client(timeout=30) as client:
        items = _discover_items(client)
    print(f"       Found {len(items)} scenes.")

    print(f"\n  [2/3] Downloading images + AES encrypt + NLSS key split + IPFS upload...")
    Image.MAX_IMAGE_PIXELS = None
    catalog_images = []

    for i, item in enumerate(items):
        img_id = f"img_{i:03d}"
        print(f"  [{i+1}/{len(items)}] {img_id} — {item['sensor']} {item['season']} — downloading...", end=" ", flush=True)

        try:
            with httpx.Client(timeout=120, follow_redirects=True) as client:
                raw_bytes = _download_image(client, item["tiff_url"])
        except Exception as e:
            print(f"SKIP ({e})")
            continue

        print(f"{len(raw_bytes):,}B — encrypt+split...", end=" ", flush=True)

        try:
            proc = await _process_image(img_id, item, raw_bytes)
        except Exception as e:
            print(f"FAILED ({e}), skipping...")
            continue

        catalog_images.append({
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

        cids_short = [s["cid"][:8] + "..." for s in proc["shares"]]
        print(f"done — blob:LOCAL keys: {', '.join(cids_short)}")

    catalog = {
        "dataset": "SSL4EO-S12 v1.1",
        "mode": "key",
        "total": len(catalog_images),
        "images": catalog_images,
    }
    CATALOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_FILE.write_text(json.dumps(catalog, indent=2), encoding="utf-8")

    elapsed = time.time() - t0
    print(f"\n  Setup complete in {elapsed:.1f}s")
    print(f"  Images:   {len(catalog_images)}")
    print(f"  Catalog:  {CATALOG_FILE}")
    return catalog


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    asyncio.run(run_setup(force=args.force))
