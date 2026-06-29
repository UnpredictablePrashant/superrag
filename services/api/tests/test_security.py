from app.core.security import (
    decrypt_secret,
    encrypt_secret,
    generate_otp,
    hash_secret,
    verify_secret,
)


def test_otp_hash_round_trip() -> None:
    code = generate_otp()
    assert len(code) == 6
    hashed = hash_secret(code)
    assert verify_secret(code, hashed)
    assert not verify_secret("000000" if code != "000000" else "111111", hashed)


def test_provider_secret_encryption_round_trip() -> None:
    encrypted = encrypt_secret("sk-test-secret")
    assert encrypted != "sk-test-secret"
    assert decrypt_secret(encrypted) == "sk-test-secret"
