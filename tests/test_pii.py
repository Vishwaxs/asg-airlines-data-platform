import re

from src.pii import hmac_token, mask_email, mask_name, mask_phone, passenger_surrogate_key

PEPPER = "test-pepper-not-the-real-one"


def test_aadhaar_zfill_unifies_the_same_identity():
    # Same underlying Aadhaar, three lengths as int64 storage left it.
    ten = passenger_surrogate_key("7345678901", PEPPER)
    eleven = passenger_surrogate_key("07345678901", PEPPER)
    twelve = passenger_surrogate_key("007345678901", PEPPER)
    assert ten == eleven == twelve


def test_without_zfill_the_same_identity_splits():
    # This is the failure the zfill prevents: hashing the raw digits gives
    # one person two surrogate keys.
    assert hmac_token("7345678901", PEPPER) != hmac_token("007345678901", PEPPER)


def test_token_is_keyed_not_plain_hash():
    assert passenger_surrogate_key("123456789012", PEPPER) != passenger_surrogate_key(
        "123456789012", "a-different-pepper"
    )


def test_token_shape():
    token = passenger_surrogate_key(123456789012, PEPPER)
    assert re.fullmatch(r"PSG_[0-9a-f]{16}", token)


def test_token_is_deterministic_across_calls():
    assert passenger_surrogate_key(123456789012, PEPPER) == passenger_surrogate_key(
        123456789012, PEPPER
    )


def test_mask_email_keeps_shape_not_identity():
    assert mask_email("rakesh.kumar@example.com") == "r***r@example.com"
    assert "rakesh" not in mask_email("rakesh.kumar@example.com")


def test_mask_email_short_local_part():
    assert mask_email("ab@example.com") == "a***@example.com"


def test_mask_phone_keeps_last_four():
    assert mask_phone("+91-9876543210") == "+91-XXXXXX3210"


def test_mask_name_drops_full_surname():
    assert mask_name("Priya", "Sharma") == "Priya S."
    assert mask_name("Priya", None) == "Priya"
    assert mask_name("Priya", "") == "Priya"
