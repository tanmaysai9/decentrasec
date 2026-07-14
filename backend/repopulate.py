#!/usr/bin/env python3
"""Clear all data and repopulate 100 satellite images with NLSS key shares.

Usage:
    cd backend
    python3 repopulate.py
"""
import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).parent
SAT_DATA = BASE / "data" / "satellite"

def main():
    print("=" * 60)
    print("  REPOPULATE — clearing all data + re-uploading 100 images")
    print("=" * 60)

    # 1. Clear manifests
    mf = BASE / "manifests.json"
    if mf.exists():
        mf.write_text("{}", encoding="utf-8")
        print("  [x] manifests.json cleared")

    # 2. Clear satellite catalog + data dirs
    for subdir in ["blobs", "raw", "thumbnails", "shares"]:
        d = SAT_DATA / subdir
        if d.exists():
            shutil.rmtree(d)
            print(f"  [x] data/satellite/{subdir}/ removed")

    cat = SAT_DATA / "catalog.json"
    if cat.exists():
        cat.write_text("{}", encoding="utf-8")
        print("  [x] data/satellite/catalog.json cleared")

    nodes_f = SAT_DATA / "nodes.json"
    if nodes_f.exists():
        nodes_f.unlink()
        print("  [x] data/satellite/nodes.json removed")

    # 3. Run satellite setup
    print("\n  Starting satellite setup (downloads + NLSS + IPFS)...\n")
    from satellite.setup import run_setup
    asyncio.run(run_setup(force=True))

    print("\n" + "=" * 60)
    print("  Repopulate complete!")
    print("=" * 60)

if __name__ == "__main__":
    main()
