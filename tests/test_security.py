"""Tests for core/security.py — Password hashing, JWT tokens."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi import HTTPException
from core.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    TokenData,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)


class TestPasswordHashing:
    def test_hash_returns_string(self):
        hashed = hash_password("secret123")
        assert isinstance(hashed, str)
        assert hashed != "secret123"

    def test_hash_is_bcrypt(self):
        hashed = hash_password("test")
        assert hashed.startswith("$2b$")

    def test_verify_correct_password(self):
        hashed = hash_password("mypassword")
        assert verify_password("mypassword", hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("mypassword")
        assert verify_password("wrongpassword", hashed) is False

    def test_different_hashes_for_same_password(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2  # bcrypt uses random salt


class TestJWTTokens:
    def test_create_token_returns_string(self):
        token = create_access_token({"user_id": 1})
        assert isinstance(token, str)
        assert len(token) > 20

    def test_decode_valid_token(self):
        token = create_access_token({"user_id": 42, "extra": "data"})
        payload = decode_access_token(token)
        assert payload["user_id"] == 42
        assert payload["extra"] == "data"
        assert "exp" in payload

    def test_decode_invalid_token_raises(self):
        with pytest.raises(HTTPException) as exc_info:
            decode_access_token("invalid.token.here")
        assert exc_info.value.status_code == 401

    def test_decode_tampered_token_raises(self):
        token = create_access_token({"user_id": 1})
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(HTTPException) as exc_info:
            decode_access_token(tampered)
        assert exc_info.value.status_code == 401

    def test_roundtrip_user_id(self):
        for uid in [1, 99, 1000]:
            token = create_access_token({"user_id": uid})
            payload = decode_access_token(token)
            assert payload["user_id"] == uid


class TestTokenData:
    def test_default_none(self):
        td = TokenData()
        assert td.user_id is None

    def test_with_value(self):
        td = TokenData(user_id=5)
        assert td.user_id == 5


class TestConstants:
    def test_algorithm(self):
        assert ALGORITHM == "HS256"

    def test_expire_minutes(self):
        assert ACCESS_TOKEN_EXPIRE_MINUTES == 60
