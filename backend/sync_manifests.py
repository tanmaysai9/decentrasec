#!/usr/bin/env python3
"""Sync satellite catalog into manifests.json for archive history.
No re-encryption or re-upload — reads existing catalog.json only.

Usage:
    cd backend
    python3 sync_manifests.py
"""
import json
from pathlib import Path

BASE = Path(__file__).parent
CATALOG_FILE = BASE / "data" / "satellite" / "catalog.json"
MANIFESTS_FILE = BASE / "manifests.json"
OWNER_ADDRESS = "0xA1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4E5F6A1B2"

catalog = json.loads(CATALOG_FILE.read_text())
images = catalog.get("images", [])

manifests = {}
for img in images:
    shares = img.get("shares", [])
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
        "upload_duration_ms": None,
        "stage_durations": {},
        "created_at": img.get("acquisition_date", "") + "T00:00:00Z",
    }

MANIFESTS_FILE.write_text(json.dumps(manifests, indent=2), encoding="utf-8")
print(f"Wrote {len(manifests)} manifest entries to {MANIFESTS_FILE}")
