# Proposal: Polymarket Secrets Vault

## Why
The current `core/config.py` stores a hardcoded `secret_key` in plain text and reads all
secrets via pydantic-settings from a single `.env` file. This is acceptable for operational
config (URLs, thresholds) but completely unacceptable for a wallet private key that controls
real on-chain USDC funds on Polygon. A leaked private key means total, irreversible loss of
trading capital. The existing pattern must be replaced before any trading code touches a wallet.

Additionally there is no audit log — every signed order, kill-switch activation, and config
change must be traceable with a tamper-evident record stored separately from the main database.

## What Changes
- `core/secrets_vault.py` (new): envelope-encrypted storage for wallet private key. Key material
  never written to disk unencrypted; loaded only into memory at runtime via PBKDF2-HMAC-SHA256
  KDF from a master password. Falls back to env var when vault absent (paper-mode / CI).
- `core/audit_log.py` (new): append-only SQLite journal (`data/audit.db`) with SHA-256 row
  chaining — tampering any past row breaks the chain and is detectable. Records: order signed,
  order submitted, order cancelled, kill-switch activated, vault unlocked, config changed.
- `core/config.py` (updated): split into `OperationalConfig` (non-sensitive, pydantic-settings)
  and `SecretConfig` (sensitive, loaded exclusively from vault or env var). Hardcoded
  `secret_key` default removed.
- `core/rate_limiter.py` (new): token-bucket rate limiter — prevents the trading loop from
  submitting more than N orders per hour regardless of loop cadence.
- `.env.example` updated with all Polymarket env vars documented but values redacted.

## Impact
- Affected code: `core/config.py`, `core/secrets_vault.py`, `core/audit_log.py`,
  `core/rate_limiter.py`, `data/audit.db`, `.env.example`
- Breaking change: YES — `core/config.py` API changes; callers updated in same task
- User benefit: Wallet private key never touches disk unencrypted; full tamper-evident audit
  trail of every trade action; rate limiting prevents runaway order submission.

Source: docs/analysis/alphacota-polymarket-autonomous-trader/
