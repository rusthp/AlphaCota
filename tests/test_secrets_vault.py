"""Tests for core/secrets_vault.py"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def tmp_vault(tmp_path, monkeypatch):
    """Redirect vault path to a temp directory for each test."""
    import core.secrets_vault as sv
    vault_path = tmp_path / "data" / ".vault"
    monkeypatch.setattr(sv, "_VAULT_PATH", vault_path)
    yield vault_path


# ---------------------------------------------------------------------------
# init_vault
# ---------------------------------------------------------------------------


def test_init_vault_creates_file(tmp_vault):
    from core.secrets_vault import init_vault
    init_vault("password123")
    assert tmp_vault.exists()


def test_init_vault_is_noop_if_exists(tmp_vault):
    from core.secrets_vault import init_vault
    init_vault("password123")
    mtime1 = tmp_vault.stat().st_mtime
    init_vault("different-password")
    mtime2 = tmp_vault.stat().st_mtime
    assert mtime1 == mtime2  # file untouched


# ---------------------------------------------------------------------------
# store_secret + load_secret — round trip
# ---------------------------------------------------------------------------


def test_round_trip(tmp_vault):
    from core.secrets_vault import init_vault, store_secret, load_secret
    init_vault("pw")
    store_secret("MY_KEY", "super-secret-value", "pw")
    result = load_secret("MY_KEY", "pw")
    assert result == "super-secret-value"


def test_round_trip_binary_like_value(tmp_vault):
    from core.secrets_vault import init_vault, store_secret, load_secret
    init_vault("pw")
    value = "0x" + "ab" * 32  # looks like a private key hex
    store_secret("PRIVATE_KEY", value, "pw")
    assert load_secret("PRIVATE_KEY", "pw") == value


def test_multiple_secrets_independent(tmp_vault):
    from core.secrets_vault import init_vault, store_secret, load_secret
    init_vault("pw")
    store_secret("A", "alpha", "pw")
    store_secret("B", "beta", "pw")
    assert load_secret("A", "pw") == "alpha"
    assert load_secret("B", "pw") == "beta"


def test_overwrite_secret(tmp_vault):
    from core.secrets_vault import init_vault, store_secret, load_secret
    init_vault("pw")
    store_secret("KEY", "old", "pw")
    store_secret("KEY", "new", "pw")
    assert load_secret("KEY", "pw") == "new"


# ---------------------------------------------------------------------------
# Wrong password
# ---------------------------------------------------------------------------


def test_wrong_password_raises_value_error(tmp_vault):
    from core.secrets_vault import init_vault, store_secret, load_secret
    init_vault("correct")
    store_secret("X", "value", "correct")
    with pytest.raises(ValueError, match="Decryption failed"):
        load_secret("X", "wrong-password")


def test_missing_secret_raises_key_error(tmp_vault):
    from core.secrets_vault import init_vault, load_secret
    init_vault("pw")
    with pytest.raises(KeyError, match="not found"):
        load_secret("DOES_NOT_EXIST", "pw")


def test_no_vault_raises_file_not_found(tmp_vault):
    from core.secrets_vault import load_secret
    with pytest.raises(FileNotFoundError):
        load_secret("X", "pw")


# ---------------------------------------------------------------------------
# Env-var fallback
# ---------------------------------------------------------------------------


def test_env_fallback_when_no_vault(tmp_vault, monkeypatch):
    from core.secrets_vault import load_secret_with_env_fallback
    monkeypatch.setenv("MY_SECRET", "from-env")
    result = load_secret_with_env_fallback("MY_SECRET", password=None, env_var="MY_SECRET")
    assert result == "from-env"


def test_env_fallback_when_password_is_none(tmp_vault, monkeypatch):
    from core.secrets_vault import init_vault, store_secret, load_secret_with_env_fallback
    init_vault("pw")
    store_secret("KEY", "from-vault", "pw")
    monkeypatch.setenv("KEY", "from-env")
    # password=None → skip vault, use env
    result = load_secret_with_env_fallback("KEY", password=None, env_var="KEY")
    assert result == "from-env"


def test_vault_takes_priority_over_env(tmp_vault, monkeypatch):
    from core.secrets_vault import init_vault, store_secret, load_secret_with_env_fallback
    init_vault("pw")
    store_secret("KEY", "from-vault", "pw")
    monkeypatch.setenv("KEY", "from-env")
    result = load_secret_with_env_fallback("KEY", password="pw", env_var="KEY")
    assert result == "from-vault"


def test_raises_when_neither_vault_nor_env(tmp_vault):
    from core.secrets_vault import load_secret_with_env_fallback
    with pytest.raises(RuntimeError, match="not found"):
        load_secret_with_env_fallback("MISSING", password=None, env_var="MISSING_ENV_VAR_THAT_DOESNT_EXIST")


# ---------------------------------------------------------------------------
# list_secrets + secret_exists
# ---------------------------------------------------------------------------


def test_list_secrets(tmp_vault):
    from core.secrets_vault import init_vault, store_secret, list_secrets
    init_vault("pw")
    store_secret("A", "1", "pw")
    store_secret("B", "2", "pw")
    names = list_secrets()
    assert set(names) == {"A", "B"}


def test_secret_exists(tmp_vault):
    from core.secrets_vault import init_vault, store_secret, secret_exists
    init_vault("pw")
    store_secret("A", "1", "pw")
    assert secret_exists("A") is True
    assert secret_exists("B") is False


def test_list_secrets_empty_when_no_vault(tmp_vault):
    from core.secrets_vault import list_secrets
    assert list_secrets() == []
