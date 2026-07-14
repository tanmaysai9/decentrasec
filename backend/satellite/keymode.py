"""Key-mode crypto helper for the satellite module.

Pipeline: gzip -> AES-256-GCM (ciphertext blob, kept local) -> the 32-byte AES
key is split with Non-Linear Secret Sharing (NLSS / DMaya) into threshold shares
that are distributed to IPFS nodes. Only the small key shares touch IPFS; the
bulk ciphertext never leaves the server.
"""

import gzip

from crypto.aes import generate_key, encrypt as aes_encrypt, decrypt as aes_decrypt
from crypto import dmaya as dmaya_mod

KEY_FILE = "key.bin"


def _classify(all_shares):
    index_files = {}
    shares = []
    for rel_path in sorted(all_shares.keys()):
        fname = rel_path.rsplit("/", 1)[-1] if "/" in rel_path else rel_path
        data = all_shares[rel_path]
        if fname == "index.txt" or fname.endswith(".json") or fname.endswith(".txt"):
            index_files[rel_path] = data
        else:
            shares.append((rel_path, data))
    return index_files, shares


def encrypt_image(raw_bytes):
    """Returns (blob_bytes, index_files, key_shares, compressed_len).

    index_files: {rel_path: bytes} of NLSS metadata (kept in the catalog).
    key_shares:  list of (rel_path, bytes) threshold shares to distribute.
    """
    compressed = gzip.compress(raw_bytes, compresslevel=6)
    aes_key = generate_key()
    blob = aes_encrypt(compressed, aes_key)

    all_shares = dmaya_mod.encrypt(aes_key, KEY_FILE)["shares"]
    index_files, key_shares = _classify(all_shares)
    return blob, index_files, key_shares, len(compressed)


def decrypt_image(blob_bytes, index_files, key_shares_fetched):
    """Recover the AES key via NLSS, decrypt the blob, gunzip.

    index_files:        {rel_path: bytes} from the catalog.
    key_shares_fetched: {rel_path: bytes} fetched from IPFS nodes.
    """
    full = dict(index_files)
    full.update(key_shares_fetched)
    aes_key = dmaya_mod.decrypt(full, KEY_FILE)
    compressed = aes_decrypt(blob_bytes, aes_key)
    return gzip.decompress(compressed)
