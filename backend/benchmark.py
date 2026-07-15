#!/usr/bin/env python3
"""Benchmark the DecentraSec pipeline with large files.

Generates synthetic images of various sizes and runs them through the
full pipeline: encrypt → NLSS split → distribute → reconstruct.

Usage:
    cd backend
    python3 benchmark.py                    # default sizes
    python3 benchmark.py --sizes 100,500,1000,5000  # custom MB sizes
    python3 benchmark.py --no-ipfs          # skip IPFS upload (encrypt+split only)
"""
import argparse
import asyncio
import base64
import io
import json
import os
import sys
import time
from pathlib import Path

from PIL import Image
Image.MAX_IMAGE_PIXELS = None

sys.path.insert(0, str(Path(__file__).parent))

from crypto.aes import generate_key, encrypt as aes_encrypt, decrypt as aes_decrypt
from crypto import dmaya as dmaya_mod
from crypto.hash import sha256
from config import NODE_NAMES, NODE_IPS
from ipfs.node import upload_to_node, fetch_from_node


def make_test_image(size_mb):
    """Generate a synthetic TIFF of approximately the given size in MB."""
    target_bytes = size_mb * 1024 * 1024
    channels = 3
    bytes_per_pixel = channels
    total_pixels = target_bytes // bytes_per_pixel
    side = int(total_pixels ** 0.5)
    side = min(side, 30000)  # PIL limit for TIFF is large, but cap at 30k

    img = Image.new("RGB", (side, side))
    px = img.load()
    for x in range(side):
        for y in range(side):
            px[x, y] = ((x * 7) % 256, (y * 13) % 256, ((x + y) * 3) % 256)

    buf = io.BytesIO()
    img.save(buf, format="TIFF", compression="raw")
    return buf.getvalue()


def make_test_bytes(size_mb):
    """Generate random bytes of approximately the given size in MB."""
    import secrets
    target = size_mb * 1024 * 1024
    chunk = 1024 * 1024
    data = b""
    while len(data) < target:
        data += secrets.token_bytes(min(chunk, target - len(data)))
    return data


def classify(shares):
    essential = {}
    key_shares = []
    for rp in sorted(shares.keys()):
        fname = rp.rsplit("/", 1)[-1] if "/" in rp else rp
        if fname == "index.txt" or fname.endswith(".txt") or fname.endswith(".json"):
            essential[rp] = shares[rp]
        else:
            key_shares.append((rp, shares[rp]))
    return essential, key_shares


async def run_benchmark(sizes, do_ipfs=True):
    results = []

    print("=" * 70)
    print("  DecentraSec Benchmark — Encrypt → NLSS Split → Distribute → Reconstruct")
    print("=" * 70)

    for size_mb in sizes:
        print(f"\n{'─' * 50}")
        print(f"  Size: {size_mb} MB")
        print(f"{'─' * 50}")

        row = {"size_mb": size_mb}
        timers = {}

        # Generate test data
        t0 = time.monotonic()
        if size_mb <= 500:
            file_data = make_test_image(size_mb)
        else:
            file_data = make_test_bytes(size_mb)
        timers["generate"] = round((time.monotonic() - t0) * 1000)
        actual_mb = len(file_data) / (1024 * 1024)
        print(f"  Generated: {actual_mb:.1f} MB ({timers['generate']}ms)")

        # SHA-256
        t0 = time.monotonic()
        file_hash = sha256(file_data)
        timers["hash"] = round((time.monotonic() - t0) * 1000)
        print(f"  SHA-256:   {timers['hash']}ms")

        # AES encrypt
        t0 = time.monotonic()
        key = generate_key()
        blob = aes_encrypt(file_data, key)
        timers["aes_encrypt"] = round((time.monotonic() - t0) * 1000)
        print(f"  AES enc:   {timers['aes_encrypt']}ms ({len(blob) / 1024 / 1024:.1f} MB blob)")

        # NLSS key split
        t0 = time.monotonic()
        all_shares = dmaya_mod.encrypt(key, "key.bin")["shares"]
        essential, key_shares = classify(all_shares)
        timers["nlss_split"] = round((time.monotonic() - t0) * 1000)
        print(f"  NLSS split: {timers['nlss_split']}ms ({len(key_shares)} shares)")

        # IPFS distribute
        if do_ipfs:
            t0 = time.monotonic()
            uploaded = []
            for idx, (rel_path, share_data) in enumerate(key_shares):
                node = NODE_NAMES[idx % len(NODE_NAMES)]
                safe_name = rel_path.replace("/", "_")
                cid = await upload_to_node(node, share_data, f"bench_{safe_name}")
                uploaded.append((node, cid, rel_path))
                print(f"    {node}: {cid[:20]}...", flush=True)
            timers["ipfs_distribute"] = round((time.monotonic() - t0) * 1000)
            print(f"  IPFS dist: {timers['ipfs_distribute']}ms")

            # IPFS fetch + reconstruct
            t0 = time.monotonic()
            fetched_shares = {}
            for node, cid, rel_path in uploaded:
                data = await fetch_from_node(node, cid)
                fetched_shares[rel_path] = data
            timers["ipfs_fetch"] = round((time.monotonic() - t0) * 1000)
            print(f"  IPFS fetch: {timers['ipfs_fetch']}ms")
        else:
            fetched_shares = {rp: d for rp, d in key_shares}

        # NLSS reconstruct key
        t0 = time.monotonic()
        all_back = dict(essential)
        all_back.update(fetched_shares)
        recovered_key = dmaya_mod.decrypt(all_back, "key.bin")
        timers["nlss_reconstruct"] = round((time.monotonic() - t0) * 1000)
        key_match = recovered_key == key
        print(f"  NLSS recon: {timers['nlss_reconstruct']}ms (key match: {key_match})")

        # AES decrypt
        t0 = time.monotonic()
        recovered_data = aes_decrypt(blob, recovered_key)
        timers["aes_decrypt"] = round((time.monotonic() - t0) * 1000)
        data_match = recovered_data == file_data
        print(f"  AES dec:   {timers['aes_decrypt']}ms (data match: {data_match})")

        row["timers"] = timers
        row["actual_mb"] = round(actual_mb, 1)
        row["blob_mb"] = round(len(blob) / (1024 * 1024), 1)
        row["n_shares"] = len(key_shares)
        row["integrity"] = key_match and data_match
        row["total_ms"] = sum(timers.values())
        row["throughput_mbps"] = round(actual_mb / (row["total_ms"] / 1000), 1)

        print(f"\n  TOTAL: {row['total_ms']}ms ({row['throughput_mbps']} MB/s)")
        print(f"  INTEGRITY: {'PASS' if row['integrity'] else 'FAIL'}")

        results.append(row)

    # Summary table
    print(f"\n{'=' * 70}")
    print("  SUMMARY")
    print(f"{'=' * 70}")
    print(f"  {'Size':>8}  {'AES enc':>8}  {'NLSS':>8}  {'IPFS dist':>10}  {'IPFS fetch':>11}  {'NLSS rec':>9}  {'AES dec':>8}  {'Total':>8}  {'MB/s':>6}  {'OK':>4}")
    print(f"  {'─'*8}  {'─'*8}  {'─'*8}  {'─'*10}  {'─'*11}  {'─'*9}  {'─'*8}  {'─'*8}  {'─'*6}  {'─'*4}")
    for r in results:
        t = r["timers"]
        ipfs_d = t.get("ipfs_distribute", "—")
        ipfs_f = t.get("ipfs_fetch", "—")
        print(f"  {r['actual_mb']:>7.1f}M  {t['aes_encrypt']:>7}ms  {t['nlss_split']:>7}ms  {str(ipfs_d):>9}ms  {str(ipfs_f):>10}ms  {t['nlss_reconstruct']:>8}ms  {t['aes_decrypt']:>7}ms  {r['total_ms']:>7}ms  {r['throughput_mbps']:>5.1f}  {'Y' if r['integrity'] else 'N':>3}")

    # Save JSON
    out = Path(__file__).parent / "benchmark_results.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\n  Results saved to {out}")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Benchmark DecentraSec pipeline")
    parser.add_argument("--sizes", default="1,10,50,100,500",
                        help="Comma-separated file sizes in MB (default: 1,10,50,100,500)")
    parser.add_argument("--no-ipfs", action="store_true",
                        help="Skip IPFS upload/fetch (encrypt+split only)")
    args = parser.parse_args()

    sizes = [int(s.strip()) for s in args.sizes.split(",")]
    asyncio.run(run_benchmark(sizes, do_ipfs=not args.no_ipfs))


if __name__ == "__main__":
    main()
