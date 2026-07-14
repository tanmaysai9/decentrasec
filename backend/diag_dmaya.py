"""Run this on the SERVER to diagnose DMaya output + classification."""
import os, sys, json, base64, secrets

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("DMaya diagnostic — testing on this machine")
print("=" * 60)

from crypto import dmaya as dm

test_key = secrets.token_bytes(32)
print(f"\n1. Test key: {test_key.hex()} ({len(test_key)} bytes)")

print("\n2. DMaya encrypt...")
result = dm.encrypt(test_key, "key.bin")
all_shares = result["shares"]
print(f"   Files produced: {len(all_shares)}")
for rp in sorted(all_shares.keys()):
    data = all_shares[rp]
    try:
        data.decode("utf-8")
        ftype = "TEXT"
    except:
        ftype = "BINARY"
    print(f"   - {rp}  ({len(data)} bytes, {ftype})")

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

print("\n4. DMaya decrypt (all files together)...")
reconstructed = dm.decrypt(all_shares, "key.bin")
print(f"   Reconstructed: {len(reconstructed)} bytes")
print(f"   Match: {reconstructed == test_key}")

print("\n5. DMaya decrypt (classified: essential + key_shares)...")
all_back = dict(essential)
for rp, d in key_shares:
    all_back[rp] = d
reconstructed2 = dm.decrypt(all_back, "key.bin")
print(f"   Reconstructed: {len(reconstructed2)} bytes")
print(f"   Match: {reconstructed2 == test_key}")

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
print("Done. If essential=1 and key_shares=4, classification is correct.")
print("If decrypt Match=True, DMaya works on this machine.")
print("=" * 60)
