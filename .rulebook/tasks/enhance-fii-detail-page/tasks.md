## 1. Backend — Score FII-Specific (`core/quant_engine.py`)
- [x] 1.1 Implement `calculate_fii_score(data)` returning 4 sub-scores: fundamentos, rendimento, risco, liquidez (each /25)
- [x] 1.2 Write tests for `calculate_fii_score` → `tests/test_quant_engine.py`

## 2. Backend — Expand GET /api/fii/{ticker} (`api/main.py`)
- [x] 2.1 Add `price_history` — last 7 months closing prices via yfinance `[{month, price}]`
- [x] 2.2 Add `dividend_history` — last 7 months DPS via FundsExplorer + yfinance fallback `[{month, value}]`
- [x] 2.3 Add `score_breakdown` — `{fundamentos, rendimento, risco, liquidez, total}` from `calculate_fii_score`
- [x] 2.4 Add `fund_info` — `{administrador, cnpj, patrimonio_liquido, num_cotistas}` from CVM/FundsExplorer
- [x] 2.5 Add extra indicators: `cap_rate`, `volatilidade_30d`, `num_imoveis`, `num_locatarios`
- [x] 2.6 Update `tests/test_api.py` to cover new response fields

## 3. Frontend — FIIDetailPage (`frontend/src/pages/FIIDetailPage.tsx`)
- [x] 3.1 Add Price History card — AreaChart (Recharts) for 7-month closing prices
- [x] 3.2 Add Dividends per Share card — BarChart (Recharts) for 7-month dividends
- [x] 3.3 Add Score breakdown card — four Progress bars (Fundamentos, Rendimento, Risco, Liquidez /25)
- [x] 3.4 Add expanded indicators — Cap Rate, Volatilidade 30d, Nº de Imóveis, Nº de Locatários
- [x] 3.5 Add Fund Info card — Administrador, CNPJ, Nº de Cotistas, Patrimônio Líquido
- [x] 3.6 Add Favourites toggle button in header (star icon, localStorage)

## 4. Frontend — ScannerPage (`frontend/src/pages/ScannerPage.tsx`)
- [x] 4.1 Add "Meus Favoritos" toggle button — filters to starred FIIs only
- [x] 4.2 Responsive: hide P/VP on `<sm`, add horizontal scroll wrapper on mobile

## 5. Frontend — PortfolioPage responsive (`frontend/src/pages/PortfolioPage.tsx`)
- [x] 5.1 KPI cards wrap to 1-column below 480px
- [x] 5.2 Table scrolls horizontally on `<md`

## 6. Data Layer — Integrar `mercados` library
- [x] 6.1 Install `mercados` (PythonicCafe) — CVM/B3/BCB official data
- [x] 6.2 Create `data/mercados_client.py` wrapping B3, CVM, FundosNet
- [x] 6.3 Add `mercados>=0.2.0` to `requirements.txt`
- [x] 6.4 Write tests for `data/mercados_client.py` → `tests/test_mercados_client.py` (30 tests)

## 7. API services layer (`frontend/src/services/api.ts`)
- [x] 7.1 Add TypeScript types: PricePoint, DividendPoint, ScoreBreakdown, FundInfo, extended FIIDetail
- [x] 7.2 Existing hook `useFIIDetail(ticker)` returns extended type automatically

## 8. Verification
- [x] 8.1 Full test suite: 751 tests passing
- [x] 8.2 Black check passes (98 files unchanged)
- [x] 8.3 Frontend builds without errors (`npm run build` in `frontend/`)
