"""Run this on the SERVER to diagnose DMaya + base64 wrapper.
Usage:  cd backend && python diag_dmaya.py
"""
import os, sys, json, secrets, subprocess, platform

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DMAYA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crypto", "DMaya1.7")

print("=" * 60)
print("DMaya diagnostic — testing on this machine")
print("=" * 60)
print(f"Platform: {platform.system()} {platform.machine()}")

# ---- 0. Check base64 wrappers ----
print("\n0. base64 wrapper check...")
for name in ("base64", "base64.exe"):
    p = os.path.join(DMAYA_DIR, name)
    if os.path.isfile(p):
        perm = oct(os.stat(p).st_mode)[-3:]
        print(f"   {name}: EXISTS (perm={perm})")
        if platform.system() != "Windows":
            r = subprocess.run(["file", p], capture_output=True, text=True)
            print(f"     {r.stdout.strip()}")
    else:
        print(f"   {name}: MISSING")

# Clear old log
log_path = "/tmp/dmaya_base64.log"
if os.path.isfile(log_path):
    os.remove(log_path)

# ---- 1. DMaya encrypt ----
from crypto import dmaya as dm

test_key = secrets.token_bytes(32)
print(f"\n1. Test key: {test_key.hex()} ({len(test_key)} bytes)")

print("\n2. DMaya encrypt...")
try:
    result = dm.encrypt(test_key, "key.bin")
    all_shares = result["shares"]
    print(f"   Files produced: {len(all_shares)}")
    for rp in sorted(all_shares.keys()):
        data = all_shares[rp]
        try:
            data.decode("utf-8")
            ftype = "TEXT"
        except Exception:
            ftype = "BINARY"
        print(f"   - {rp}  ({len(data)} bytes, {ftype})")
        if ftype == "TEXT" and len(data) > 0:
            print(f"       content: {data[:200].decode('utf-8', errors='replace')}")
except Exception as e:
    print(f"   ERROR: {e}")
    # Show base64 log
    if os.path.isfile(log_path):
        print(f"\n   --- /tmp/dmaya_base64.log ---")
        with open(log_path) as f:
            print(f.read())
    sys.exit(1)

# ---- 3. Classification ----
print("\n3. Classification...")
essential = {}
key_shares = []
for rp in sorted(all_shares.keys()):
    fname = rp.rsplit("/", 1)[-1] if "/" in rp else rp
    data = all_shares[rp]
    if fname == "index.txt" or fname.endswith(".json") or fname.endswith(".txt"):
        essential[rp] = data
    else:
        key_shares.append((rp, data))
print(f"   Essential (local): {len(essential)}")
print(f"   Key shares (nodes): {len(key_shares)}")

# ---- 4. DMaya decrypt ----
print("\n4. DMaya decrypt (all files together)...")
try:
    reconstructed = dm.decrypt(all_shares, "key.bin")
    print(f"   Reconstructed: {len(reconstructed)} bytes")
    print(f"   Match: {reconstructed == test_key}")
except Exception as e:
    print(f"   ERROR: {e}")

# ---- 5. base64 call log ----
print(f"\n5. base64 call log ({log_path})...")
if os.path.isfile(log_path):
    with open(log_path) as f:
        content = f.read()
    print(content if content.strip() else "   (empty — base64 was never called!)")
else:
    print("   (no log file — base64 was never called)")

# ---- 6. Manifest check ----
print("\n6. Check manifest of last upload...")
try:
    from store import load_manifests
    manifests = load_manifests()
    for mid, m in manifests.items():
        ks = m.get("key_shares", [])
        ki = m.get("key_index", {})
        print(f"   {mid}: key_shares={len(ks)}, key_index={len(ki)}")
        for s in ks:
            print(f"     share {s['index']}: node={s['node']} cid={s['cid'][:20]}...")
except Exception as e:
    print(f"   Error reading manifests: {e}")

print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"  Files from encrypt: {len(all_shares)} (expect 5: 1 index + 4 .dat)")
print(f"  Essential:          {len(essential)} (expect 1)")
print(f"  Key shares:         {len(key_shares)} (expect 4)")
try:
    print(f"  Decrypt match:      {reconstructed == test_key}")
except Exception:
    print(f"  Decrypt match:      ERROR")
print("=" * 60)
