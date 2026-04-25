# Polymarket Live Trader Runbook

Operational guide for the AlphaCota Polymarket live trading system.

---

## Architecture Overview

```
polymarket_loop.py          — Main event loop (entry point)
  ├─ polymarket_preflight.py    — Pre-start safety checks
  ├─ polymarket_client.py       — Gamma API + CLOB API
  ├─ polymarket_ledger.py       — WAL-mode SQLite (5 tables)
  ├─ polymarket_score.py        — AI-powered market scoring
  ├─ polymarket_risk.py         — Kelly criterion + position limits
  ├─ polymarket_decision_engine.py — Trade signal generation
  ├─ polymarket_executor.py     — Live order submission (EIP-712)
  ├─ polymarket_monitor.py      — Position price tracking
  ├─ polymarket_exit_engine.py  — Exit rule evaluation
  └─ polymarket_observability.py — Structured JSONL logging
```

---

## Prerequisites

### Environment Variables (`.env`)

```bash
POLYMARKET_MODE=live              # live | paper
POLYGON_RPC_URL=https://...       # Alchemy Polygon RPC
POLYMARKET_API_KEY=...            # CLOB API key
POLYMARKET_API_SECRET=...         # CLOB API secret
POLYMARKET_PRIVATE_KEY_ENC=...    # AES-256-GCM encrypted key (from vault)
VAULT_PASSWORD=...                # PBKDF2 vault password
OPENROUTER_API_KEY=...            # For AI probability estimation
```

### Vault Setup (one-time)

Encrypt the private key using the vault tool:

```bash
python -m core.polymarket_vault encrypt
# Enter private key when prompted
# Sets POLYMARKET_PRIVATE_KEY_ENC in .env
```

---

## Pre-flight Checks

The system runs pre-flight automatically before starting. To run manually:

```bash
python -m core.polymarket_preflight
```

Pre-flight verifies:
1. **RPC reachable** — `eth_blockNumber` returns a valid hex block number
2. **Private key present** — `POLYMARKET_PRIVATE_KEY_ENC` is set and decryptable
3. **USDC balance ≥ $20** — wallet has sufficient funds
4. **CTF allowance granted** — ERC-20 approval to the Conditional Token Framework Exchange
5. **CLOB API key valid** — authenticated request to CLOB API succeeds

If any check fails, the service will not start.

---

## Starting the Trader

### Systemd (production)

```bash
systemctl start alphacota-trader
systemctl status alphacota-trader
journalctl -u alphacota-trader -f
```

### Manual (development/testing)

```bash
# Paper mode (safe, uses synthetic wallet)
python -m core.polymarket_loop --mode=paper --iterations=3

# Live mode (real orders)
python -m core.polymarket_loop --mode=live
```

---

## Loop Behavior

Each iteration (default sleep: 300s):

1. Check kill-switch file (`data/POLYMARKET_KILL`)
2. Discover tradeable markets (Gamma API, volume/spread/age filters)
3. Score each market (AI edge + liquidity + time + copy + news)
4. Apply Kelly criterion and position limits
5. Submit new orders for approved decisions
6. Monitor all open positions (update prices in DB)
7. Apply exit rules to each position
8. Log iteration summary to JSONL

**On 3 consecutive errors**: re-runs preflight before continuing.

---

## Hard Limits (non-configurable)

| Limit | Value |
|-------|-------|
| Max position size | $50 USD |
| Max daily loss | $10 USD |
| Max open positions | 5 |
| Max same-category positions | 2 |
| Min market score to trade | 40 / 100 |
| Kelly cap | 25% of bankroll |

Exceeding `MAX_POSITION_USD` or `MAX_DAILY_LOSS_USD` raises `HardLimitExceeded` and the order is rejected before signing.

---

## Kill Switch

To halt all trading immediately without stopping the service:

```bash
touch data/POLYMARKET_KILL
```

The loop checks this file at the start of every iteration and before every `close_live_position()` call. Remove the file to resume:

```bash
rm data/POLYMARKET_KILL
```

To stop the service entirely:

```bash
systemctl stop alphacota-trader
```

---

## Exit Rules

Positions are closed automatically when any rule fires:

| Rule | Condition |
|------|-----------|
| `take_profit` | Unrealized PnL ≥ +50% |
| `stop_loss` | Unrealized PnL ≤ −30% |
| `time_stop` | Days to resolution < 2 AND price moved < 2% in 24h |
| `score_inversion` | Re-scored market dropped > 30 points |
| `resolution_hold` | Market resolved — collect winnings |

---

## Observability

Structured logs are written to `logs/polymarket_YYYY-MM-DD.jsonl` (daily rotation).

Each line is a JSON object:

```json
{"ts": 1713096000.0, "event": "order_filled", "mode": "live", "order_id": "abc", "fill": 0.62}
```

**Valid event types:**
- `order_attempt` — order submitted to CLOB
- `order_filled` — order confirmed filled
- `order_cancelled` — order cancelled/rejected
- `position_closed` — position exited with realized PnL
- `hard_limit_hit` — order blocked by hard limit
- `kill_switch_active` — kill-switch file detected

### Tailing live logs

```bash
tail -f logs/polymarket_$(date +%Y-%m-%d).jsonl | python -m json.tool
```

### Querying daily PnL from logs

```bash
python - <<'EOF'
import json, pathlib, datetime

today = datetime.date.today().isoformat()
log = pathlib.Path(f"logs/polymarket_{today}.jsonl")
pnl = sum(
    json.loads(l).get("realized_pnl", 0)
    for l in log.read_text().splitlines()
    if json.loads(l).get("event") == "position_closed"
)
print(f"Realized PnL today: ${pnl:.2f}")
EOF
```

---

## Database

SQLite WAL-mode at `data/polymarket.db` (configurable via `POLYMARKET_DB_PATH`).

### Schema

| Table | Purpose |
|-------|---------|
| `pm_markets` | Discovered markets cache |
| `pm_orders` | Order history (idempotent inserts) |
| `pm_positions` | Open positions with live prices |
| `pm_trades` | Closed trade history with realized PnL |
| `pm_pnl_snapshots` | Daily PnL snapshots for reporting |

### Useful queries

```sql
-- Open positions
SELECT condition_id, direction, size_usd, entry_price, current_price, unrealized_pnl
FROM pm_positions
ORDER BY opened_at DESC;

-- Today's realized PnL
SELECT SUM(realized_pnl) as daily_pnl
FROM pm_trades
WHERE closed_at > strftime('%s', date('now'));

-- Win rate
SELECT
  COUNT(*) as total,
  SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
  ROUND(100.0 * SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_pct
FROM pm_trades WHERE mode = 'live';
```

---

## API Endpoints

The FastAPI server exposes live status at `http://localhost:8000`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/polymarket/status` | GET | Wallet health, open positions count |
| `/polymarket/positions` | GET | All open positions |
| `/polymarket/orders` | GET | Recent order history |
| `/polymarket/pnl` | GET | Realized PnL summary |
| `/polymarket/live-status` | GET | Loop health, last iteration time |
| `/polymarket/kill` | POST | Activate kill-switch |

---

## Incident Response

### Service won't start

1. Check pre-flight output: `python -m core.polymarket_preflight`
2. Verify `.env` variables are set: `cat .env | grep POLYMARKET`
3. Check RPC URL is reachable: `curl -s $POLYGON_RPC_URL`
4. Verify USDC balance via Polygon explorer

### Large unexpected loss

1. Activate kill-switch immediately: `touch data/POLYMARKET_KILL`
2. Stop service: `systemctl stop alphacota-trader`
3. Inspect recent trades: `sqlite3 data/polymarket.db "SELECT * FROM pm_trades ORDER BY closed_at DESC LIMIT 20;"`
4. Review JSONL logs: `tail -100 logs/polymarket_$(date +%Y-%m-%d).jsonl`
5. Do NOT restart without investigating root cause

### Position stuck open

1. Check if kill-switch is active (would block `close_live_position`)
2. Verify CLOB API connectivity
3. Check USDC balance for sufficient gas
4. Manually close via CLOB web interface if needed

### Database corruption

WAL mode prevents most corruption. If corruption occurs:

```bash
# Check integrity
sqlite3 data/polymarket.db "PRAGMA integrity_check;"

# Restore from backup (kept automatically at data/polymarket.db.bak)
cp data/polymarket.db.bak data/polymarket.db
```

---

## Deployment

```bash
# Deploy service file
cp systemd/alphacota-trader.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable alphacota-trader

# Start
systemctl start alphacota-trader

# Monitor
journalctl -u alphacota-trader -f --no-pager
```

### Resource limits (systemd)

- Memory: 512 MB max
- CPU: 50% quota
- Restart: on-failure, 30s backoff
