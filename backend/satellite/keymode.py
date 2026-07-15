"""Key-mode crypto helper for the satellite module.

Pipeline: encrypt raw bytes (ciphertext blob, kept local) -> the key is split
with DMaya into an essential share (index.txt, stays with user) + key shares
(.dat files, distributed to IPFS nodes).
"""

from crypto.aes import generate_key, encrypt as aes_encrypt, decrypt as aes_decrypt
from crypto.aes import encrypt_stream, decrypt_stream
from crypto import dmaya as dmaya_mod

KEY_FILE = "key.bin"


def _classify(all_shares):
    essential = {}
    shares = []
    for rel_path in sorted(all_shares.keys()):
        fname = rel_path.rsplit("/", 1)[-1] if "/" in rel_path else rel_path
        data = all_shares[rel_path]
        if fname == "index.txt" or fname.endswith(".json") or fname.endswith(".txt"):
            essential[rel_path] = data
        else:
            shares.append((rel_path, data))
    return essential, shares


def encrypt_image(raw_bytes):
    """Returns (blob_bytes, essential_files, key_shares).

    essential_files: {rel_path: bytes} of the essential share (kept in catalog).
    key_shares:      list of (rel_path, bytes) threshold shares to distribute.
    """
    key = generate_key()
    blob = aes_encrypt(raw_bytes, key)

    all_shares = dmaya_mod.encrypt(key, KEY_FILE)["shares"]
    essential_files, key_shares = _classify(all_shares)
    return blob, essential_files, key_shares


def decrypt_image(blob_bytes, essential_files, key_shares_fetched):
    """Recover the key, decrypt the blob (legacy in-memory GCM format).

    essential_files:    {rel_path: bytes} from the catalog.
    key_shares_fetched: {rel_path: bytes} fetched from IPFS nodes.
    """
    full = dict(essential_files)
    full.update(key_shares_fetched)
    key = dmaya_mod.decrypt(full, KEY_FILE)
    return aes_decrypt(blob_bytes, key)


def decrypt_image_stream(blob_path, out_path, essential_files, key_shares_fetched):
    """Recover the key, stream-decrypt blob to out_path (streaming AES-GCM).

    essential_files:    {rel_path: bytes} from the catalog.
    key_shares_fetched: {rel_path: bytes} fetched from IPFS nodes.
    """
    full = dict(essential_files)
    full.update(key_shares_fetched)
    key = dmaya_mod.decrypt(full, KEY_FILE)
    decrypt_stream(blob_path, out_path, key)
