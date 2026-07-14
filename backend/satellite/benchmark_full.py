#!/usr/bin/env python3
"""
benchmark_full.py — Enhanced NLSS + IPFS benchmark (legacy full-payload path).

NOTE: The production runtime now uses KEY MODE (AES-256-GCM on the data, kept
local; only the 32-byte AES key is NLSS/DMaya-split to nodes). This script
retains the legacy full-payload split (NLSS over the whole compressed file)
for comparison/baseline purposes. See benchmark.py for the key-mode benchmark.

Matches the legacy DecentraSec design:
  * Each share is placed on ONE specific storage node via its daemon API
    (upload_to_node -> :5001/api/v0/add, pin on that node). NO replication of shares.
  * The manifest (small JSON mapping share -> node/CID) goes through the
    Cluster API (upload_json -> :9094) and IS replicated.
  * Retrieval fetches the essential index + all data shares from their specific
    nodes (fetch_from_node -> that node's :8080 gateway). The scheme is 3-of-4
    cryptographically, but the current decoder requires all share files present.

Adds vs benchmark.py:
  * Multiple trials per file        -> mean +/- std for every stage.
  * Plain-IPFS baseline             -> raw file up+retrieve on one node (no NLSS).
  * Storage-expansion               -> total share bytes vs original size.
  * CSV + JSON output               -> easy paste into the paper's Table IV.

Run on the bootstrap node:
    cd ~/decentrasec/backend
    source venv/bin/activate
    # put 5-7 test images of varied sizes in ./bench_data/
    BENCH_TRIALS=5 python satellite/benchmark_full.py
"""

import asyncio
import csv
import json
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import NODE_NAMES
from ipfs.node import upload_to_node, fetch_from_node
from ipfs.cluster import upload_json
from ipfs.gateway import fetch_json

try:
    import crypto.dmaya as dmaya_mod
except Exception as e:
    print("ERROR: NLSS (crypto.dmaya) not available:", e)
    sys.exit(1)

BENCH_DIR = Path(__file__).parent.parent / "bench_data"
TRIALS = int(os.getenv("BENCH_TRIALS", "5"))
OUT_JSON = BENCH_DIR / "benchmark_results_full.json"
OUT_CSV = BENCH_DIR / "benchmark_results_full.csv"

_META_NAMES = ("index", "index.txt")
_META_SUFFIXES = (".json", ".txt")


def _classify(all_shares):
    """Split share dict into (data_entries, meta_entries), each list of (rel, bytes)."""
    data, meta = [], []
    for rel, sd in all_shares.items():
        fname = rel.rsplit("/", 1)[-1] if "/" in rel else rel
        if fname in _META_NAMES or fname.endswith(_META_SUFFIXES):
            meta.append((rel, sd))
        else:
            data.append((rel, sd))
    data.sort(key=lambda x: x[0])
    meta.sort(key=lambda x: x[0])
    return data, meta


def _stats(values):
    values = list(values)
    return {
        "mean": statistics.mean(values),
        "std": statistics.pstdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
        "n": len(values),
    }


def _ms(t0):
    return (time.monotonic() - t0) * 1000.0


async def baseline_plain_ipfs(raw_bytes, label, node_name):
    """Raw file (no NLSS): upload to one node, retrieve from it."""
    t0 = time.monotonic()
    cid = await upload_to_node(node_name, raw_bytes, label)
    up_ms = _ms(t0)
    t1 = time.monotonic()
    await fetch_from_node(node_name, cid)
    ret_ms = _ms(t1)
    return up_ms, ret_ms


async def nlss_round_trip(raw_bytes, file_name):
    """One full NLSS round trip (legacy full-payload split) on the direct-to-node path."""
    # 1. NLSS encrypt -> shares
    t0 = time.monotonic()
    res = dmaya_mod.encrypt(raw_bytes, file_name)
    enc_ms = _ms(t0)
    all_shares = res["shares"]
    data_entries, meta_entries = _classify(all_shares)
    all_entries = meta_entries + data_entries  # index first, then data

    share_bytes_total = sum(len(sd) for _, sd in all_entries)

    # 2. Place each share on a specific node (round-robin); replicate the manifest.
    t1 = time.monotonic()
    placement = {}  # rel -> {"node","cid","kind"}
    for i, (rel, sd) in enumerate(all_entries):
        node = NODE_NAMES[i % len(NODE_NAMES)]
        cid = await upload_to_node(node, sd, f"{file_name}_{rel}")
        kind = "meta" if (rel, sd) in [(r, s) for r, s in meta_entries] else "data"
        placement[rel] = {"node": node, "cid": cid, "kind": kind}
    manifest = {"file": file_name, "shares": placement}
    manifest_cid = await upload_json(json.dumps(manifest).encode())
    up_ms = _ms(t1)

    # 3. Retrieve: fetch manifest, then the essential index + ALL data shares.
    #    The scheme is 3-of-4 cryptographically, but the current decoder enumerates
    #    every share directory and requires all share files present, so we fetch
    #    all four data shares (graceful 3-of-4 reconstruction is a cryptographic
    #    property not yet exposed by the decoder binary).
    t2 = time.monotonic()
    manifest = await fetch_json(manifest_cid)
    fetched = {}
    meta_rels = [r for r, v in manifest["shares"].items() if v["kind"] == "meta"]
    data_rels = [r for r, v in manifest["shares"].items() if v["kind"] == "data"]
    for rel in meta_rels + data_rels:
        v = manifest["shares"][rel]
        fetched[rel] = await fetch_from_node(v["node"], v["cid"])
    ret_ms = _ms(t2)

    # 4. NLSS decrypt (essential index + data shares)
    t3 = time.monotonic()
    decrypted = dmaya_mod.decrypt(dict(fetched), file_name)
    dec_ms = _ms(t3)

    total_ms = enc_ms + up_ms + ret_ms + dec_ms
    return {
        "enc_ms": enc_ms,
        "up_ms": up_ms,
        "ret_ms": ret_ms,
        "dec_ms": dec_ms,
        "total_ms": total_ms,
        "integrity_ok": decrypted == raw_bytes,
        "share_bytes_total": share_bytes_total,
        "num_data_shares": len(data_entries),
        "num_meta_shares": len(meta_entries),
    }


async def main():
    files = (
        sorted(BENCH_DIR.glob("*.tif"))
        + sorted(BENCH_DIR.glob("*.bin"))
        + sorted(BENCH_DIR.glob("*.dat"))
    )
    only = os.getenv("BENCH_ONLY", "").strip()
    if only:
        files = [f for f in files if only.lower() in f.name.lower()]
    if not files:
        print(f"No test files in {BENCH_DIR}" + (f" matching BENCH_ONLY='{only}'" if only else ""))
        print("Place .tif/.bin/.dat files there and re-run.")
        return

    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 74)
    print(f"  NLSS + IPFS Benchmark — direct-to-node path")
    print(f"  Trials/file = {TRIALS} | Nodes = {NODE_NAMES}")
    print(f"  Test files: {BENCH_DIR}  ({len(files)} files)")
    print("=" * 74)

    results = []
    for f in files:
        size = f.stat().st_size
        size_mb = size / 1024 / 1024
        raw = f.read_bytes()
        print(f"\n--- {f.name} ({size_mb:.1f} MB) ---")

        enc, up, ret, dec, tot, exp = [], [], [], [], [], []
        integrity_all = True
        nd = nm = None
        for t in range(TRIALS):
            try:
                r = await nlss_round_trip(raw, f.name)
            except Exception as e:
                print(f"  trial {t+1}: FAILED - {e!r} (skipping trial)")
                continue
            enc.append(r["enc_ms"]); up.append(r["up_ms"]); ret.append(r["ret_ms"])
            dec.append(r["dec_ms"]); tot.append(r["total_ms"])
            exp.append(r["share_bytes_total"] / size if size else 0.0)
            integrity_all = integrity_all and r["integrity_ok"]
            nd, nm = r["num_data_shares"], r["num_meta_shares"]
            print(f"  trial {t+1}: enc {r['enc_ms']:.0f} | up {r['up_ms']:.0f} | "
                  f"ret {r['ret_ms']:.0f} | dec {r['dec_ms']:.0f} | "
                  f"total {r['total_ms']:.0f} ms | "
                  f"integrity {'OK' if r['integrity_ok'] else 'FAIL'}")

        if not enc:
            print(f"  !! no successful trials for {f.name}; skipping file")
            continue

        # Plain-IPFS baseline (no NLSS) on the first node
        b_up, b_ret = [], []
        for _ in range(max(3, TRIALS)):
            u, rr = await baseline_plain_ipfs(raw, f"{f.name}_baseline", NODE_NAMES[0])
            b_up.append(u); b_ret.append(rr)

        s_enc, s_up = _stats(enc), _stats(up)
        s_ret, s_dec = _stats(ret), _stats(dec)
        s_tot = _stats(tot)
        s_exp = _stats(exp)
        s_bup, s_bret = _stats(b_up), _stats(b_ret)

        row = {
            "file": f.name,
            "size_mb": round(size_mb, 1),
            "num_data_shares": nd,
            "num_meta_shares": nm,
            "integrity_all_ok": integrity_all,
            "nlss_enc_ms_mean": round(s_enc["mean"]),
            "nlss_enc_ms_std": round(s_enc["std"]),
            "ipfs_upload_ms_mean": round(s_up["mean"]),
            "ipfs_upload_ms_std": round(s_up["std"]),
            "ipfs_retrieve_ms_mean": round(s_ret["mean"]),
            "ipfs_retrieve_ms_std": round(s_ret["std"]),
            "nlss_decrypt_ms_mean": round(s_dec["mean"]),
            "nlss_decrypt_ms_std": round(s_dec["std"]),
            "total_ms_mean": round(s_tot["mean"]),
            "total_ms_std": round(s_tot["std"]),
            "total_sec_mean": round(s_tot["mean"] / 1000, 1),
            "storage_expansion_x": round(s_exp["mean"], 2),
            "baseline_ipfs_upload_ms_mean": round(s_bup["mean"]),
            "baseline_ipfs_retrieve_ms_mean": round(s_bret["mean"]),
        }
        results.append(row)
        print(f"  -> total {row['total_sec_mean']} s (+/-{row['total_ms_std']/1000:.1f}), "
              f"expansion {row['storage_expansion_x']}x, "
              f"baseline up+ret {row['baseline_ipfs_upload_ms_mean']+row['baseline_ipfs_retrieve_ms_mean']} ms")

    payload = {
        "trials_per_file": TRIALS,
        "scheme": "NLSS (legacy full-payload): 4 data shares + essential index, need 3 data + index",
        "share_placement": "one share per node (no replication); manifest cluster-replicated",
        "files": results,
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2))
    print(f"\nJSON  -> {OUT_JSON}")

    with OUT_CSV.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)
    print(f"CSV   -> {OUT_CSV}")
    print("=" * 74)
    print("Done. Paste mean columns into Table IV; *_std for error bars;")
    print("storage_expansion_x for storage-overhead; compare NLSS total vs")
    print("(baseline_ipfs_upload+retrieve) to show NLSS overhead.")


if __name__ == "__main__":
    asyncio.run(main())
