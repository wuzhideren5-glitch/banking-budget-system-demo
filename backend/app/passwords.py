from __future__ import annotations

import base64
import hashlib
import secrets


def verify_daily_password(stored_hash: str | None, raw_password: str) -> bool:
    if not stored_hash:
        return False
    try:
        algo, rounds_str, salt_b64, digest_b64 = stored_hash.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        rounds = int(rounds_str)
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        digest = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
        calc = hashlib.pbkdf2_hmac("sha256", raw_password.encode("utf-8"), salt, rounds)
        return secrets.compare_digest(calc, digest)
    except Exception:
        return False


def hash_daily_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return (
        "pbkdf2_sha256$120000$"
        + base64.urlsafe_b64encode(salt).decode("ascii")
        + "$"
        + base64.urlsafe_b64encode(digest).decode("ascii")
    )
