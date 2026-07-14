"""Key-mode crypto helper for the satellite module.

Pipeline: encrypt raw bytes (ciphertext blob, kept local) -> the key is split
into shares that are distributed to IPFS nodes. The first share is the
essential share; the rest are key shares.
"""

from crypto.aes import generate_key, encrypt as aes_encrypt, decrypt as aes_decrypt
from crypto import dmaya as dmaya_mod

KEY_FILE = "key.bin"


def encrypt_image(raw_bytes):
    """Returns (blob_bytes, all_shares).

    all_shares: list of (rel_path, bytes) — all shares to distribute.
    """
    key = generate_key()
    blob = aes_encrypt(raw_bytes, key)

    raw_shares = dmaya_mod.encrypt(key, KEY_FILE)["shares"]
    all_shares = sorted(raw_shares.items())
    return blob, all_shares


def decrypt_image(blob_bytes, all_shares_fetched):
    """Recover the key, decrypt the blob.

    all_shares_fetched: {rel_path: bytes} fetched from IPFS nodes.
    """
    key = dmaya_mod.decrypt(all_shares_fetched, KEY_FILE)
    return aes_decrypt(blob_bytes, key)
