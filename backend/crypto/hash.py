import hashlib
import secrets


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str, chunk_size: int = 64 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def mock_merkle_root(cids: list[str]) -> str:
    combined = "".join(sorted(cids))
    return "0x" + hashlib.sha256(combined.encode()).hexdigest()


def mock_tx_hash(manifest_id: str) -> str:
    raw = hashlib.sha256(manifest_id.encode()).hexdigest()
    return "0x" + raw
