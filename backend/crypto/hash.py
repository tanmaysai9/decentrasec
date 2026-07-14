import hashlib
import secrets


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def mock_merkle_root(cids: list[str]) -> str:
    combined = "".join(sorted(cids))
    return "0x" + hashlib.sha256(combined.encode()).hexdigest()


def mock_tx_hash(manifest_id: str) -> str:
    raw = hashlib.sha256(manifest_id.encode()).hexdigest()
    return "0x" + raw
