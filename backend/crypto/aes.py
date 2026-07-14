import os

from Crypto.Cipher import AES

NONCE_SIZE = 12
TAG_SIZE = 16
KEY_SIZE = 32


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
