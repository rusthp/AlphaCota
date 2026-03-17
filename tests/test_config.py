"""Tests for core/config.py — Settings and env loading."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import Settings, settings


class TestSettings:
    def test_default_database_path(self):
        s = Settings()
        assert s.database_path == "alphacota.db"

    def test_default_secret_key(self):
        s = Settings()
        assert len(s.secret_key) > 10

    def test_singleton_exists(self):
        assert settings is not None
        assert isinstance(settings, Settings)

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("DATABASE_PATH", "custom.db")
        s = Settings()
        assert s.database_path == "custom.db"
