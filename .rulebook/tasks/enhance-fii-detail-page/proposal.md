# Proposal: Enhance FII Detail Page, Scanner & Scoring

## Why

The current FII Detail page is minimal compared to the Lovable reference design and lacks critical
visualisation and data that investors rely on. Several distinct problems exist:

1. **Score always shows 0** — `api/main.py` fetched `"score_final"` from `evaluate_company()` which
   returns the key `"final_score"` (key mismatch). Same bug existed in `FIIDetailPage.tsx`.
   **Status: already patched.**

2. **Score algorithm is wrong for FIIs** — `calculate_quality_score()` uses stock-market metrics
   (`pl`, `roe`, `roa`, `revenue_growth`, `debt_to_equity`, `current_ratio`) that are meaningless
   for real-estate investment trusts. FIIs must be scored on DY, P/VP, vacância, liquidez, and
   dividend consistency.

3. **FII Detail page is sparse** — The reference design shows a price-history line chart (7 months),
   a dividends-per-share bar chart (7 months), a 4-dimension score breakdown (Fundamentos,
   Rendimento, Risco, Liquidez — each out of 25), expanded indicators (Cap Rate, Volatilidade 30d,
   Nº de Imóveis, Nº de Locatários), and a fund-info card (Administrador, CNPJ, Nº de Cotas,
   Patrimônio Líquido). None of these appear in the current implementation.

4. **No way to view favourites** — Stars can be toggled in the Scanner but there is no filter to
   display only favourited FIIs, making the feature invisible and useless.

5. **Mobile layout incomplete** — Scanner table columns do not collapse gracefully below 640 px;
   Portfolio KPI cards overflow on very small screens.

## What Changes

### Backend (`api/main.py`, `core/quant_engine.py`)

- Add `calculate_fii_score(data)` in `core/quant_engine.py` using FII-specific metrics,
  returning four sub-scores (fundamentos, rendimento, risco, liquidez) each capped at 25.
- Expand `GET /api/fii/{ticker}` response to include:
  - `price_history`: list of `{month, price}` objects for the last 7 months (yfinance).
  - `dividend_history`: list of `{month, value}` for the last 7 months (FundsExplorer
    `historico_dividendos` + CVM proventos fallback).
  - `score_breakdown`: `{fundamentos, rendimento, risco, liquidez, total}`.
  - `fund_info`: `{administrador, cnpj, num_cotas, patrimonio_liquido}` from CVM + FundsExplorer.
  - `cap_rate`, `volatilidade_30d`, `num_imoveis`, `num_locatarios` where available.

### Frontend (`frontend/src/pages/FIIDetailPage.tsx`)

- **Price History card** — AreaChart (Recharts) for 7-month closing prices.
- **Dividends per Share card** — BarChart (Recharts) for 7-month dividends.
- **Score breakdown card** — Four Progress bars (Fundamentos, Rendimento, Risco, Liquidez /25).
- **Expanded indicators** — Cap Rate, Volatilidade (30d), Nº de Imóveis, Nº de Locatários.
- **Fund Info card** — Administrador, CNPJ, Nº de Cotas, Patrimônio Líquido.
- **Favourites button** in header (star icon, localStorage).

### Frontend (`frontend/src/pages/ScannerPage.tsx`)

- **Favourites filter toggle** — "Meus Favoritos" button next to Filtros; filters to starred FIIs.

### Responsive fixes

- Scanner: hide P/VP on `<sm`, add horizontal scroll wrapper on mobile.
- Portfolio: KPI cards wrap to 1-column below 480 px; table scrolls horizontally on `<md`.

## Impact

- Affected specs: `frontend`, `api`, `core`
- Affected code: `core/quant_engine.py`, `api/main.py`, `frontend/src/pages/FIIDetailPage.tsx`,
  `frontend/src/pages/ScannerPage.tsx`, `frontend/src/pages/PortfolioPage.tsx`
- Breaking change: NO — all additions are new optional fields; existing consumers unaffected.
- User benefit: Rich FII analytics matching the reference design; working score; visible favourites;
  better mobile experience.
