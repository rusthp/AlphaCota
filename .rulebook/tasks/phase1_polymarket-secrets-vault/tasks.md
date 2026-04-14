## 1. Config Split
- [x] 1.1 Read `core/config.py` and split into `OperationalConfig` + `SecretConfig`; remove hardcoded `secret_key`
- [x] 1.2 Update `.env.example` with all Polymarket vars (`POLYMARKET_PRIVATE_KEY`, `POLYMARKET_MODE`, `POLYMARKET_MAX_POSITION_USD`, `POLYMARKET_MAX_DAILY_LOSS_USD`, `POLYGON_RPC_URL`)

## 2. Secrets Vault
- [x] 2.1 Implement `core/secrets_vault.py`: `init_vault(password)`, `store_secret(name, value)`, `load_secret(name) -> str`; PBKDF2-HMAC-SHA256 KDF, AES-256-GCM encryption, vault stored at `data/.vault` (gitignored)
- [x] 2.2 Env-var fallback: when vault absent or `POLYMARKET_MODE=paper`, load `POLYMARKET_PRIVATE_KEY` directly from env

## 3. Audit Log
- [x] 3.1 Implement `core/audit_log.py`: `log_event(event_type, payload)` writing to `data/audit.db` with SHA-256 chain — each row stores `prev_hash`; `verify_chain() -> bool`
- [x] 3.2 Add event types: `ORDER_SIGNED`, `ORDER_SUBMITTED`, `ORDER_CANCELLED`, `KILL_SWITCH`, `VAULT_UNLOCKED`, `CONFIG_CHANGED`

## 4. Rate Limiter
- [x] 4.1 Implement `core/rate_limiter.py`: token-bucket `RateLimiter(max_per_hour)` with `acquire() -> bool`; thread-safe; configurable from `OperationalConfig`

## 5. Tail
- [x] 5.1 Write `tests/test_secrets_vault.py`: encrypt/decrypt round-trip, wrong password raises, env fallback
- [x] 5.2 Write `tests/test_audit_log.py`: chain integrity, tamper detection breaks chain, all event types
- [x] 5.3 Write `tests/test_rate_limiter.py`: burst allowed, limit enforced, refill over time
- [x] 5.4 Run `ruff check` + `mypy core/secrets_vault.py core/audit_log.py core/rate_limiter.py` — zero errors
- [x] 5.5 Run `pytest tests/test_secrets_vault.py tests/test_audit_log.py tests/test_rate_limiter.py -v` — all pass
