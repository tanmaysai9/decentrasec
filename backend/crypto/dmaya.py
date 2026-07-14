import subprocess
import tempfile
import os
import platform
import shutil
import json
from pathlib import Path

_USE_MONO = platform.system() != "Windows"

_DIR = str(Path(__file__).parent)
_DMaya_DIR = (
    os.path.join(_DIR, "DMaya1.7")
    if os.path.isdir(os.path.join(_DIR, "DMaya1.7"))
    else os.path.join(_DIR, "DMaya")
)

# ---------------------------------------------------------------------------
# base64 wrapper for Linux
# ---------------------------------------------------------------------------
# DMaya (Windows .NET) shells out to "base64" with flags like -c (create/encode)
# that GNU coreutils base64 doesn't understand.  The mono wrapper approach
# failed because base64.exe is a native Windows binary, not a .NET assembly.
#
# Instead we create a bash wrapper that translates Windows flags to GNU base64
# equivalents.  We install it as both "base64" and "base64.exe" so it is found
# regardless of how DMaya invokes the subprocess.

_B64_WRAPPER = r'''#!/bin/bash
# Auto-generated wrapper: translates Windows base64.exe flags to GNU base64
LOG="/tmp/dmaya_base64.log"
echo "$(date '+%H:%M:%S') CALL: $@" >> "$LOG"

decode=0
files=()
for arg in "$@"; do
    case "$arg" in
        -d|--decode) decode=1 ;;
        -c|-e|--encode) ;;          # encode is GNU default, drop the flag
        -w*|-*) ;;                   # ignore unknown flags
        *) files+=("$arg") ;;
    esac
done

if [ $decode -eq 1 ]; then
    op="-d"
else
    op="-w0"
fi

if [ ${#files[@]} -eq 0 ]; then
    /usr/bin/base64 $op
elif [ ${#files[@]} -eq 1 ]; then
    /usr/bin/base64 $op "${files[0]}"
elif [ ${#files[@]} -eq 2 ]; then
    /usr/bin/base64 $op "${files[0]}" > "${files[1]}"
else
    echo "  ERROR: unexpected files: ${files[@]}" >> "$LOG"
    exit 1
fi
rc=$?
echo "  rc=$rc decode=$decode nfiles=${#files[@]}" >> "$LOG"
exit $rc
'''


def _ensure_base64_wrapper():
    """Install GNU-base64 wrappers for both 'base64' and 'base64.exe'."""
    if not _USE_MONO:
        return
    for name in ("base64", "base64.exe"):
        path = os.path.join(_DMaya_DIR, name)
        with open(path, "w", newline="\n") as f:
            f.write(_B64_WRAPPER)
        os.chmod(path, 0o755)


_ensure_base64_wrapper()


def _find_binary(name):
    for d in [_DMaya_DIR, _DIR]:
        for n in [name, name + ".exe"]:
            p = os.path.join(d, n)
            if os.path.isfile(p):
                return p
    raise FileNotFoundError(
        f"DMaya binary '{name}' not found in {_DMaya_DIR} or {_DIR}"
    )


def _env_with_dmaya():
    """Prepend DMaya dirs to PATH so our base64 wrapper is found first."""
    env = os.environ.copy()
    paths = [_DMaya_DIR, "."]
    env["PATH"] = os.pathsep.join(paths) + os.pathsep + env.get("PATH", "")
    return env


def _copy_runtime(src_dir, dest_dir):
    """Copy DMaya runtime files into *dest_dir*, ensuring wrappers are exec."""
    for fname in os.listdir(src_dir):
        src = os.path.join(src_dir, fname)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(dest_dir, fname))
    if _USE_MONO:
        for name in ("base64", "base64.exe"):
            dst = os.path.join(dest_dir, name)
            if os.path.isfile(dst):
                os.chmod(dst, 0o755)


def encrypt(data: bytes, file_name: str) -> dict:
    enc_bin = _find_binary("DMaya1.7-enc")
    env = _env_with_dmaya()
    with tempfile.TemporaryDirectory() as tmpdir:
        work_dir = os.path.join(tmpdir, "dmaya_work")
        os.makedirs(work_dir)
        if os.path.isdir(_DMaya_DIR):
            _copy_runtime(_DMaya_DIR, work_dir)

        input_path = os.path.join(work_dir, file_name)
        with open(input_path, "wb") as f:
            f.write(data)

        out_dir = os.path.join(tmpdir, "dmaya_output")
        os.makedirs(out_dir)

        cmd = (["mono", enc_bin] if _USE_MONO else [enc_bin]) + [input_path, out_dir]
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=3600,
            cwd=work_dir,
            env=env,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"DMaya encrypt failed (rc={result.returncode}): "
                f"{result.stderr.decode(errors='replace')}\n"
                f"stdout: {result.stdout.decode(errors='replace')}"
            )

        shares = {}
        metadata = None
        for root, dirs, files in os.walk(out_dir):
            for fname in files:
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, out_dir).replace("\\", "/")
                with open(fpath, "rb") as f:
                    content = f.read()
                if (
                    fname.endswith(".json")
                    or fname.endswith(".txt")
                    or fname == "index"
                ):
                    try:
                        parsed = json.loads(content)
                        if metadata is None:
                            metadata = parsed
                        shares[rel] = content
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        shares[rel] = content
                else:
                    shares[rel] = content

        # ---- validation ----
        if len(shares) < 3:
            stderr = result.stderr.decode(errors="replace")
            stdout = result.stdout.decode(errors="replace")
            raise RuntimeError(
                f"DMaya encrypt produced only {len(shares)} file(s) — "
                f"expected 5+. The base64 wrapper may not be working.\n"
                f"Files: {sorted(shares.keys())}\n"
                f"stdout: {stdout[:500]}\n"
                f"stderr: {stderr[:500]}\n"
                f"Check /tmp/dmaya_base64.log for base64 call trace."
            )

        return {"shares": shares, "metadata": metadata}


def decrypt(shares: dict, file_name: str) -> bytes:
    dec_bin = _find_binary("DMaya1.7-dec")
    env = _env_with_dmaya()
    with tempfile.TemporaryDirectory() as tmpdir:
        share_dir = os.path.join(tmpdir, "dmaya_shares")
        os.makedirs(share_dir)

        for rel_path, data in shares.items():
            fpath = os.path.join(share_dir, rel_path)
            os.makedirs(os.path.dirname(fpath), exist_ok=True)
            with open(fpath, "wb") as f:
                f.write(data)

        work_dir = os.path.join(tmpdir, "dmaya_work")
        os.makedirs(work_dir)
        if os.path.isdir(_DMaya_DIR):
            _copy_runtime(_DMaya_DIR, work_dir)

        output_path = os.path.join(tmpdir, "output", file_name)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        cmd = (["mono", dec_bin] if _USE_MONO else [dec_bin]) + [share_dir, output_path]
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=3600,
            cwd=work_dir,
            env=env,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"DMaya decrypt failed (rc={result.returncode}): "
                f"{result.stderr.decode(errors='replace')}\n"
                f"stdout: {result.stdout.decode(errors='replace')}"
            )

        with open(output_path, "rb") as f:
            data = f.read()

        if len(data) == 0:
            stderr = result.stderr.decode(errors="replace")
            stdout = result.stdout.decode(errors="replace")
            raise RuntimeError(
                f"DMaya decrypt produced 0 bytes.\n"
                f"Shares provided: {len(shares)} ({sorted(shares.keys())})\n"
                f"stdout: {stdout[:500]}\n"
                f"stderr: {stderr[:500]}\n"
                f"Check /tmp/dmaya_base64.log for base64 call trace."
            )

        return data
