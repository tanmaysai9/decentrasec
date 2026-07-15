import os
import struct

from Crypto.Cipher import AES

NONCE_SIZE = 12
TAG_SIZE = 16
KEY_SIZE = 32

_CHUNK_SIZE = 64 * 1024 * 1024  # 64 MB per chunk


def generate_key() -> bytes:
    return os.urandom(KEY_SIZE)


def encrypt(data: bytes, key: bytes) -> bytes:
    nonce = os.urandom(NONCE_SIZE)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(data)
    return nonce + tag + ciphertext


def decrypt(blob: bytes, key: bytes) -> bytes:
    if len(blob) < NONCE_SIZE + TAG_SIZE:
        raise ValueError("Ciphertext blob too short for AES-GCM")
    nonce = blob[:NONCE_SIZE]
    tag = blob[NONCE_SIZE : NONCE_SIZE + TAG_SIZE]
    ciphertext = blob[NONCE_SIZE + TAG_SIZE :]
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    return cipher.decrypt_and_verify(ciphertext, tag)


# ---------------------------------------------------------------------------
# Streaming AES-GCM via the cryptography library (uses AES-NI hardware accel)
# Format per chunk: [4-byte BE length][12-byte nonce][ciphertext + 16-byte tag]
# ---------------------------------------------------------------------------

def encrypt_stream(in_path, out_path, key, chunk_size=_CHUNK_SIZE):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    aesgcm = AESGCM(key)
    with open(in_path, "rb") as fin, open(out_path, "wb") as fout:
        while True:
            chunk = fin.read(chunk_size)
            if not chunk:
                break
            nonce = os.urandom(12)
            ct = aesgcm.encrypt(nonce, chunk, None)
            fout.write(struct.pack(">I", len(ct)))
            fout.write(nonce)
            fout.write(ct)


def decrypt_stream(in_path, out_path, key):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    aesgcm = AESGCM(key)
    with open(in_path, "rb") as fin, open(out_path, "wb") as fout:
        while True:
            hdr = fin.read(4)
            if not hdr:
                break
            ct_len = struct.unpack(">I", hdr)[0]
            nonce = fin.read(12)
            ct = fin.read(ct_len)
            pt = aesgcm.decrypt(nonce, ct, None)
            fout.write(pt)
