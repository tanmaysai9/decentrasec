import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import NODE_NAMES
from satellite import keymode
from ipfs.node import upload_to_node, fetch_from_node


BENCH_DIR = Path(__file__).parent.parent / "bench_data"


async def benchmark():
    files = (
        sorted(BENCH_DIR.glob("*.tif"))
        + sorted(BENCH_DIR.glob("*.bin"))
        + sorted(BENCH_DIR.glob("*.dat"))
    )
    if not files:
        print(f"No test files found in {BENCH_DIR}")
        print("Place .tif / .bin / .dat files there and re-run.")
        return

    print("=" * 70)
    print("  NLSS Key-Mode + IPFS Benchmark")
    print("  AES-256-GCM on data (local) | NLSS splits the 32-byte AES key -> nodes")
    print(f"  Test files: {BENCH_DIR}")
    print("=" * 70)

    encrypt_times = []
    upload_times = []
    upload_sizes = []
    retrieve_times = []
    decrypt_times = []
    total_times = []
    file_sizes = []

    for f in files:
        print(f"\n--- {f.name} ({f.stat().st_size / 1024 / 1024:.1f} MB) ---")
        raw_bytes = f.read_bytes()
        file_sizes.append(f.stat().st_size)

        t0 = time.monotonic()

        # 1. AES encrypt + NLSS key split (local)
        t1 = time.monotonic()
        blob, index_files, key_shares, comp_len = keymode.encrypt_image(raw_bytes)
        encrypt_ms = round((time.monotonic() - t1) * 1000)
        encrypt_times.append(encrypt_ms)
        print(f"  AES+NLSS encrypt: {encrypt_ms:>8} ms  (blob {len(blob)/1024/1024:.1f} MB, {len(key_shares)} key shares)")

        # 2. IPFS upload (key shares only)
        placement = []
        for i, (rel_path, share_data) in enumerate(key_shares):
            node = NODE_NAMES[i % len(NODE_NAMES)]
            upload_sizes.append(len(share_data))
            t2 = time.monotonic()
            cid = await upload_to_node(node, share_data, f"{f.stem}_key_{i}")
            up_ms = round((time.monotonic() - t2) * 1000)
            upload_times.append(up_ms)
            placement.append((rel_path, node, cid))
            print(f"  IPFS upload k{i}:   {up_ms:>8} ms  ({len(share_data)} B)  CID: {cid[:20]}...")

        # 3. IPFS retrieve (key shares)
        fetched = {}
        for rel_path, node, cid in placement:
            t3 = time.monotonic()
            data = await fetch_from_node(node, cid)
            ret_ms = round((time.monotonic() - t3) * 1000)
            retrieve_times.append(ret_ms)
            fetched[rel_path] = data
            print(f"  IPFS get k{i}:      {ret_ms:>8} ms")

        # 4. NLSS recover + AES decrypt (blob local)
        t4 = time.monotonic()
        decrypted = keymode.decrypt_image(blob, index_files, fetched)
        decrypt_ms = round((time.monotonic() - t4) * 1000)
        decrypt_times.append(decrypt_ms)
        print(f"  NLSS+AES decrypt:  {decrypt_ms:>8} ms")

        total_ms = round((time.monotonic() - t0) * 1000)
        total_times.append(total_ms)
        match = decrypted == raw_bytes
        print(f"  TOTAL:             {total_ms:>8} ms  | integrity: {'PASS' if match else 'FAIL'}")

    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print(f"  Files tested:       {len(files)}")
    print(f"  File sizes:         {min(file_sizes)/1024/1024:.1f} - {max(file_sizes)/1024/1024:.1f} MB")
    print()
    print(f"  AES+NLSS Encrypt:   avg {sum(encrypt_times)/len(encrypt_times):.0f} ms")
    print(f"  IPFS Upload:        avg {sum(upload_times)/len(upload_times):.0f} ms  (avg key share {sum(upload_sizes)/len(upload_sizes):.0f} B)")
    print(f"  IPFS Retrieve:      avg {sum(retrieve_times)/len(retrieve_times):.0f} ms")
    print(f"  NLSS+AES Decrypt:   avg {sum(decrypt_times)/len(decrypt_times):.0f} ms")
    print(f"  Total End-to-End:   avg {sum(total_times)/len(total_times):.0f} ms ({sum(total_times)/len(total_times)/1000:.1f} s)")
    print("=" * 70)

    results = {
        "files_tested": len(files),
        "mode": "key",
        "file_sizes_mb": [round(s / 1024 / 1024, 1) for s in file_sizes],
        "encrypt_avg_ms": round(sum(encrypt_times) / len(encrypt_times)),
        "ipfs_upload_avg_ms": round(sum(upload_times) / len(upload_times)),
        "ipfs_retrieve_avg_ms": round(sum(retrieve_times) / len(retrieve_times)),
        "decrypt_avg_ms": round(sum(decrypt_times) / len(decrypt_times)),
        "total_avg_ms": round(sum(total_times) / len(total_times)),
        "total_avg_sec": round(sum(total_times) / len(total_times) / 1000, 1),
        "avg_key_share_bytes": round(sum(upload_sizes) / len(upload_sizes)),
    }
    out_path = BENCH_DIR / "benchmark_results.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\n  Results saved to {out_path}")


if __name__ == "__main__":
    asyncio.run(benchmark())
