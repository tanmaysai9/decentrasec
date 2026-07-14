"""Debug base64 wrapper resolution for DMaya."""
import os, sys, subprocess, tempfile, shutil, platform

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DMAYA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crypto", "DMaya1.7")

print("=== Check wrapper creation ===")
wrapper = os.path.join(DMAYA_DIR, "base64")
b64_exe = os.path.join(DMAYA_DIR, "base64.exe")
print(f"base64.exe exists: {os.path.isfile(b64_exe)}")
print(f"base64 wrapper exists: {os.path.isfile(wrapper)}")
if os.path.isfile(wrapper):
    print(f"wrapper contents:")
    with open(wrapper) as f:
        print(f.read())
    print(f"wrapper executable: {os.access(wrapper, os.X_OK)}")
else:
    print("Creating wrapper manually...")
    with open(wrapper, "w") as f:
        f.write("#!/bin/bash\n")
        f.write(f'exec mono "{b64_exe}" "$@"\n')
    os.chmod(wrapper, 0o755)
    print("Created.")

print("\n=== Test wrapper directly ===")
test_data = b"Hello World"
r = subprocess.run([wrapper, "-c", "-"], input=test_data, capture_output=True)
print(f"rc={r.returncode}")
print(f"stdout: {r.stdout[:200]}")
print(f"stderr: {r.stderr.decode(errors='replace')[:200]}")

print("\n=== Test base64.exe via mono directly ===")
r = subprocess.run(["mono", b64_exe, "--help"], capture_output=True, text=True, timeout=10)
print(f"rc={r.returncode}")
print(f"stdout: {r.stdout[:500]}")
print(f"stderr: {r.stderr[:500]}")

print("\n=== Test with PATH including DMaya dir ===")
env = os.environ.copy()
env["PATH"] = DMAYA_DIR + os.pathsep + "." + os.pathsep + env.get("PATH", "")
r = subprocess.run(["base64", "--version"], capture_output=True, text=True, env=env)
print(f"which base64 resolves to:")
r2 = subprocess.run(["which", "base64"], capture_output=True, text=True, env=env)
print(f"  {r2.stdout.strip()}")
print(f"  output: {r.stdout[:200]}")

print("\n=== Run DMaya encrypt with verbose env ===")
enc_bin = os.path.join(DMAYA_DIR, "DMaya1.7-enc.exe")
with tempfile.TemporaryDirectory() as tmpdir:
    work_dir = os.path.join(tmpdir, "work")
    os.makedirs(work_dir)
    for fname in os.listdir(DMAYA_DIR):
        src = os.path.join(DMAYA_DIR, fname)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(work_dir, fname))
    wrapper_dst = os.path.join(work_dir, "base64")
    if os.path.isfile(wrapper):
        shutil.copy2(wrapper, wrapper_dst)
        os.chmod(wrapper_dst, 0o755)

    input_path = os.path.join(work_dir, "key.bin")
    with open(input_path, "wb") as f:
        f.write(b"\x01" * 32)
    out_dir = os.path.join(tmpdir, "output")
    os.makedirs(out_dir)

    env2 = os.environ.copy()
    env2["PATH"] = work_dir + os.pathsep + DMAYA_DIR + os.pathsep + env2.get("PATH", "")

    r = subprocess.run(
        ["mono", enc_bin, input_path, out_dir],
        capture_output=True, text=True, timeout=60,
        cwd=work_dir, env=env2
    )
    print(f"rc={r.returncode}")
    print(f"STDOUT: {r.stdout[:1000]}")
    print(f"STDERR: {r.stderr[:1000]}")

    print(f"\nOutput files:")
    for root, dirs, files in os.walk(out_dir):
        for fname in files:
            fpath = os.path.join(root, fname)
            print(f"  {os.path.relpath(fpath, out_dir)}  ({os.path.getsize(fpath)} bytes)")

    print(f"\nWork dir files:")
    for f in sorted(os.listdir(work_dir)):
        print(f"  {f}")
