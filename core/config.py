from pydantic_settings import BaseSettings


class OperationalConfig(BaseSettings):
    """Non-sensitive runtime configuration — safe to log and inspect."""

    database_path: str = "alphacota.db"
    groq_api_key: str = ""
    openrouter_api_key: str = ""

    # Polymarket operational settings
    polymarket_mode: str = "paper"  # "paper" | "live"
    polymarket_max_position_usd: float = 50.0
    polymarket_max_daily_loss_usd: float = 10.0
    polygon_rpc_url: str = ""  # Alchemy/Infura HTTPS endpoint
    loop_interval_seconds: int = 300

    class Config:
        env_file = ".env"
        env_prefix = ""
        extra = "ignore"


class SecretConfig(BaseSettings):
    """Sensitive secrets — never log, never serialize to JSON."""

    secret_key: str = ""  # JWT signing key — must be set via env, never hardcoded
    polymarket_api_key: str = ""
    polymarket_api_secret: str = ""
    polymarket_private_key_enc: str = ""  # AES-256-GCM encrypted private key (hex)
    polygonscan_api_key: str = ""

    class Config:
        env_file = ".env"
        env_prefix = ""
        extra = "ignore"

    def __repr__(self) -> str:
        return "SecretConfig(*** REDACTED ***)"

    def __str__(self) -> str:
        return "SecretConfig(*** REDACTED ***)"


# ---------------------------------------------------------------------------
# Module-level singletons — import these, not the classes directly
# ---------------------------------------------------------------------------

operational = OperationalConfig()
secrets = SecretConfig()

# Legacy alias so existing code (security.py, database.py) keeps working
# without changes — settings.secret_key and settings.database_path still work.
class _LegacySettings:
    @property
    def secret_key(self) -> str:
        return secrets.secret_key

    @property
    def database_path(self) -> str:
        return operational.database_path

    @property
    def groq_api_key(self) -> str:
        return operational.groq_api_key


settings = _LegacySettings()
