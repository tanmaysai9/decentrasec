"""Diagnose DMaya binary execution on Linux."""
import os, sys, subprocess, platform, tempfile, shutil, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DMAYA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crypto", "DMaya1.7")

print("=" * 60)
print("DMaya binary diagnostic")
print("=" * 60)

print(f"\nPlatform: {platform.system()} {platform.release()}")
print(f"Python: {sys.version}")

print("\n--- mono version ---")
r = subprocess.run(["mono", "--version"], capture_output=True, text=True)
print(r.stdout[:500] if r.stdout else "no output")
if r.returncode != 0:
    print(f"ERROR: mono not found (rc={r.returncode})")

print("\n--- dotnet version (if available) ---")
r = subprocess.run(["dotnet", "--version"], capture_output=True, text=True)
print(r.stdout.strip() if r.stdout.strip() else "dotnet not installed")

print(f"\n--- DMaya directory contents ---")
for f in sorted(os.listdir(DMAYA_DIR)):
    fp = os.path.join(DMAYA_DIR, f)
    if os.path.isfile(fp):
        print(f"  {f}  ({os.path.getsize(fp)} bytes)")

enc_bin = os.path.join(DMAYA_DIR, "DMaya1.7-enc.exe")
dec_bin = os.path.join(DMAYA_DIR, "DMaya1.7-dec.exe")

print(f"\n--- Direct DMaya encrypt test ---")
with tempfile.TemporaryDirectory() as tmpdir:
    work_dir = os.path.join(tmpdir, "work")
    os.makedirs(work_dir)

    # copy runtime files
    for fname in os.listdir(DMAYA_DIR):
        src = os.path.join(DMAYA_DIR, fname)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(work_dir, fname))

    # write test input
    input_path = os.path.join(work_dir, "key.bin")
    test_data = b"\x01" * 32
    with open(input_path, "wb") as f:
        f.write(test_data)

    out_dir = os.path.join(tmpdir, "output")
    os.makedirs(out_dir)

    cmd = ["mono", enc_bin, input_path, out_dir]
    print(f"  CMD: {' '.join(cmd)}")
    print(f"  CWD: {work_dir}")

    r = subprocess.run(cmd, capture_output=True, timeout=60, cwd=work_dir)
    print(f"  Return code: {r.returncode}")
    print(f"  STDOUT: {r.stdout.decode(errors='replace')[:1000]}")
    print(f"  STDERR: {r.stderr.decode(errors='replace')[:1000]}")

    print(f"\n  Output directory contents:")
    for root, dirs, files in os.walk(out_dir):
        for fname in files:
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, out_dir)
            size = os.path.getsize(fpath)
            with open(fpath, "rb") as f:
                content = f.read()
            print(f"    {rel}  ({size} bytes)")
            try:
                print(f"      text: {content.decode('utf-8')[:200]}")
            except:
                print(f"      hex: {content.hex()[:100]}")

print("\n--- Try running WITHOUT mono (native) ---")
r = subprocess.run([enc_bin, "--help"], capture_output=True, text=True, timeout=10)
print(f"  rc={r.returncode}")
print(f"  stdout: {r.stdout[:300]}")
print(f"  stderr: {r.stderr[:300]}")

print("\n--- Check ForTesting/Linux ---")
linux_dir = os.path.join(DMAYA_DIR, "ForTesting", "Linux", "Linux")
if os.path.isdir(linux_dir):
    print(f"  Found: {linux_dir}")
    for f in sorted(os.listdir(linux_dir)):
        print(f"    {f}")
    install = os.path.join(linux_dir, "install.sh")
    if os.path.isfile(install):
        print(f"\n  install.sh contents:")
        with open(install) as f:
            print(f.read()[:1000])
else:
    print("  Not found (excluded from git)")

print("\n" + "=" * 60)
