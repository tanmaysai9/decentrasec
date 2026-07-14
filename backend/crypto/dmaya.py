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


def _ensure_base64_wrapper():
    """On Linux, DMaya calls 'base64 -c' but system base64 doesn't support -c.
    Create a wrapper script that runs the bundled base64.exe via mono."""
    if not _USE_MONO:
        return
    wrapper = os.path.join(_DMaya_DIR, "base64")
    b64_exe = os.path.join(_DMaya_DIR, "base64.exe")
    if not os.path.isfile(b64_exe):
        return
    if not os.path.isfile(wrapper):
        with open(wrapper, "w") as f:
            f.write("#!/bin/bash\n")
            f.write(f'exec mono "{b64_exe}" "$@"\n')
        os.chmod(wrapper, 0o755)


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
    env = os.environ.copy()
    paths = [_DMaya_DIR, "."]
    env["PATH"] = os.pathsep.join(paths) + os.pathsep + env.get("PATH", "")
    return env


def _copy_runtime(src_dir, dest_dir):
    for fname in os.listdir(src_dir):
        src = os.path.join(src_dir, fname)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(dest_dir, fname))
    if _USE_MONO:
        wrapper_src = os.path.join(src_dir, "base64")
        wrapper_dst = os.path.join(dest_dir, "base64")
        if os.path.isfile(wrapper_src):
            shutil.copy2(wrapper_src, wrapper_dst)
            os.chmod(wrapper_dst, 0o755)


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
            return f.read()
