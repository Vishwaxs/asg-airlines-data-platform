from __future__ import annotations

import hashlib
import hmac


def hmac_token(value: str, pepper: str, length: int = 16) -> str:
    # Plain SHA-256 over a 12-digit Aadhaar is enumerable in minutes on a
    # laptop (keyspace 10**12) and rebuilds the lookup table trivially - HMAC
    # keyed with a pepper held outside the repo makes the token useless
    # without the secret, at the cost of key management.
    digest = hmac.new(pepper.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:length]


def passenger_surrogate_key(aadhaar_id: object, pepper: str, length: int = 16) -> str:
    # aadhaar_id lost leading zeros to int64 storage upstream; zfill(12)
    # before hashing so a 10-, 11- or 12-digit representation of the same
    # identity produces the same token. Hash the raw digits and this splits
    # one person into two surrogate keys.
    normalized = str(aadhaar_id).zfill(12)
    return "PSG_" + hmac_token(normalized, pepper, length)


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        masked_local = local[:1] + "***"
    else:
        masked_local = local[0] + "***" + local[-1]
    return f"{masked_local}@{domain}"


def mask_phone(phone: str) -> str:
    last_four = phone[-4:]
    return f"+91-XXXXXX{last_four}"


def mask_name(first_name: str, last_name: str | None) -> str:
    initial = f"{last_name[0]}." if isinstance(last_name, str) and last_name else ""
    return f"{first_name} {initial}".strip()


def age_band(age: int, bands: list[tuple[int, int, str]]) -> str:
    for lo, hi, label in bands:
        if lo <= age <= hi:
            return label
    return "unknown"
