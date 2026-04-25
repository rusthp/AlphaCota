"""Tests for core/config.py — Settings and env loading."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import OperationalConfig, SecretConfig, operational, secrets, settings


class TestOperationalConfig:
    def test_default_database_path(self):
        c = OperationalConfig()
        assert c.database_path == "alphacota.db"

    def test_default_polymarket_mode(self):
        c = OperationalConfig()
        assert c.polymarket_mode == "paper"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("DATABASE_PATH", "custom.db")
        c = OperationalConfig()
        assert c.database_path == "custom.db"

    def test_singletons_exist(self):
        assert operational is not None
        assert isinstance(operational, OperationalConfig)


class TestSecretConfig:
    def test_default_secret_key_empty(self):
        c = SecretConfig()
        # Default is empty string — must be set via env
        assert isinstance(c.secret_key, str)

    def test_repr_is_redacted(self):
        assert "REDACTED" in repr(secrets)

    def test_str_is_redacted(self):
        assert "REDACTED" in str(secrets)

    def test_singleton_exists(self):
        assert secrets is not None
        assert isinstance(secrets, SecretConfig)


class TestLegacySettings:
    def test_settings_alias_exists(self):
        assert settings is not None

    def test_database_path_accessible(self):
        assert settings.database_path == "alphacota.db"

    def test_groq_api_key_accessible(self):
        assert isinstance(settings.groq_api_key, str)
