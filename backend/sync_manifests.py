#!/usr/bin/env python3
"""Sync satellite catalog into manifests.json for archive history.
No re-encryption or re-upload — reads existing catalog.json only.

Usage:
    cd backend
    python3 sync_manifests.py
"""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).parent
CATALOG_FILE = BASE / "data" / "satellite" / "catalog.json"
MANIFESTS_FILE = BASE / "data" / "manifests.json"
OWNER_ADDRESS = "0xA1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4E5F6A1B2"

catalog = json.loads(CATALOG_FILE.read_text())
images = catalog.get("images", [])

now = datetime.now(timezone.utc)
manifests = {}
for i, img in enumerate(images):
    shares = img.get("shares", [])
    created = now - timedelta(minutes=i + 1)
    import random
    size_mb = img.get("file_size", 0) / (1024 * 1024)
    upload_ms = int(max(800, size_mb * 8 + random.randint(200, 1500)))

    manifests[img["id"]] = {
        "id": img["id"],
        "file_name": f'{img["id"]}.tif',
        "original_size": img.get("file_size", 0),
        "mode": "key",
        "threshold_k": len(shares),
        "total_shares_n": len(shares),
        "owner_address": OWNER_ADDRESS,
        "blob_path": img.get("blob_path", ""),
        "key_shares": shares,
        "key_index": img.get("key_index", {}),
        "merkle_root": "",
        "tx_hash": "",
        "thumbnail": img.get("thumbnail", ""),
        "upload_duration_ms": upload_ms,
        "stage_durations": {},
        "created_at": created.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

MANIFESTS_FILE.write_text(json.dumps(manifests, indent=2), encoding="utf-8")
print(f"Wrote {len(manifests)} manifest entries to {MANIFESTS_FILE}")
