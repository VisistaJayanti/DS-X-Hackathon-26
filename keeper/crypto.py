"""Encryption at rest for uploaded documents, member profiles and the LLM response cache.

Uses Fernet (AES-128-CBC + HMAC-SHA256) from the `cryptography` package.

Key handling:
  * Production / shared machines: set CK_ENCRYPTION_KEY to a key made with
        python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  * Local development: if CK_ENCRYPTION_KEY is not set, a key is created once in ./.ck_key
    (git-ignored, owner-only permissions). Losing that file makes stored cases unreadable.
Never commit the key.
"""
import json
import os
import stat
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

ROOT = Path(__file__).resolve().parent.parent
KEY_FILE = Path(os.environ.get("CK_KEY_FILE", ROOT / ".ck_key"))
MAGIC = b"CKENC1:"  # marks encrypted files so older plain-JSON files can still be read

_fernet = None


def _key():
    env = os.environ.get("CK_ENCRYPTION_KEY")
    if env:
        return env.encode()
    if KEY_FILE.exists():
        return KEY_FILE.read_bytes().strip()
    key = Fernet.generate_key()
    KEY_FILE.write_bytes(key)
    try:
        os.chmod(KEY_FILE, stat.S_IRUSR | stat.S_IWUSR)  # 600: only the owner can read it
    except OSError:
        pass
    return key


def fernet():
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_key())
    return _fernet


def encrypt_bytes(data: bytes) -> bytes:
    return MAGIC + fernet().encrypt(data)


def decrypt_bytes(blob: bytes) -> bytes:
    if not blob.startswith(MAGIC):
        return blob  # legacy plaintext file
    try:
        return fernet().decrypt(blob[len(MAGIC):])
    except InvalidToken as e:
        raise ValueError("Cannot decrypt: wrong or missing CK_ENCRYPTION_KEY") from e


def is_encrypted(blob: bytes) -> bool:
    return blob.startswith(MAGIC)


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encrypt_bytes(json.dumps(obj, ensure_ascii=False).encode("utf-8")))


def read_json(path: Path):
    return json.loads(decrypt_bytes(path.read_bytes()).decode("utf-8"))
