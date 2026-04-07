## ADDED Requirements

### Requirement: FII-Specific Scoring Algorithm
The system SHALL calculate a FII quality score using four FII-specific sub-dimensions —
Fundamentos, Rendimento, Risco, and Liquidez — each scoring 0–25, for a combined total of 0–100.
The legacy stock-metric scoring (pl, roe, roa, debt_to_equity) MUST NOT be used for FIIs.

#### Scenario: FII with good fundamentals scores high
Given a FII with pvp=0.95, dividend_yield=0.10, vacancy_rate=0.03, daily_liquidity=10_000_000
When `calculate_fii_score()` is called with that data
Then the total score SHALL be greater than 75

#### Scenario: FII with poor fundamentals scores low
Given a FII with pvp=2.5, dividend_yield=0.03, vacancy_rate=0.30, daily_liquidity=100_000
When `calculate_fii_score()` is called with that data
Then the total score SHALL be less than 40

#### Scenario: Score breakdown is always returned
Given any FII data dict (even with missing optional fields)
When `calculate_fii_score()` is called
Then the return value SHALL contain keys fundamentos, rendimento, risco, liquidez, and total
And each sub-score SHALL be between 0 and 25

---

### Requirement: Price History in FII Detail Endpoint
The `GET /api/fii/{ticker}` endpoint SHALL return a `price_history` field containing the last
7 months of monthly closing prices sourced from yfinance.

#### Scenario: Ticker with sufficient price history
Given ticker HGLG11 has at least 7 months of price data in yfinance
When `GET /api/fii/HGLG11` is called
Then the response SHALL include `price_history` as a list of objects
And each object SHALL have a `month` string (format "MMM/YY") and a `price` float greater than 0
And the list SHALL contain exactly 7 entries

#### Scenario: Ticker with insufficient price history
Given a ticker with fewer than 7 months of available data
When `GET /api/fii/{ticker}` is called
Then `price_history` SHALL be returned as an empty list
And the response SHALL still include all other fields

---

### Requirement: Dividend History in FII Detail Endpoint
The `GET /api/fii/{ticker}` endpoint SHALL return a `dividend_history` field containing the last
7 months of dividends per share, sourced from FundsExplorer with CVM proventos as fallback.

#### Scenario: Dividend history from FundsExplorer
Given FundsExplorer `historico_dividendos` has data for ticker MXRF11
When `GET /api/fii/MXRF11` is called
Then `dividend_history` SHALL be a list of objects with `month` and `value` keys
And `value` SHALL be a positive float representing BRL per share

#### Scenario: Dividend history unavailable
Given FundsExplorer and CVM both return no dividend data for a ticker
When `GET /api/fii/{ticker}` is called
Then `dividend_history` SHALL be an empty list

---

### Requirement: Score Breakdown in FII Detail Endpoint
The `GET /api/fii/{ticker}` endpoint SHALL return a `score_breakdown` field with the four
sub-scores from `calculate_fii_score()`.

#### Scenario: Score breakdown included in response
Given any valid ticker
When `GET /api/fii/{ticker}` is called
Then the response SHALL contain `score_breakdown` with keys:
  fundamentos, rendimento, risco, liquidez (each 0–25) and total (0–100)

---

### Requirement: Fund Info in FII Detail Endpoint
The `GET /api/fii/{ticker}` endpoint SHALL return a `fund_info` field containing administrative
details sourced from CVM registry and FundsExplorer.

#### Scenario: Fund info from CVM registry
Given ticker HGLG11 exists in the CVM FII registry
When `GET /api/fii/HGLG11` is called
Then `fund_info` SHALL contain `administrador` and `cnpj` as non-empty strings

#### Scenario: Fund info partially unavailable
Given a ticker not found in CVM registry
When `GET /api/fii/{ticker}` is called
Then `fund_info` SHALL be returned with null values for missing fields
And the endpoint SHALL NOT raise a 500 error

---

### Requirement: Favourites Filter in Scanner
The Scanner page SHALL provide a toggle button labelled "Meus Favoritos" that filters the FII
table to show only tickers saved in the user's localStorage favourites.

#### Scenario: User activates favourites filter
Given the user has starred HGLG11 and MXRF11 in the Scanner
When the user clicks "Meus Favoritos"
Then the table SHALL display only HGLG11 and MXRF11
And the button SHALL show a count badge ("Favoritos (2)")

#### Scenario: No favourites saved
Given the user has not starred any FII
When the user clicks "Meus Favoritos"
Then the table SHALL be empty
And a helper message SHALL be shown ("Nenhum favorito salvo")

#### Scenario: Deactivating favourites filter
Given the favourites filter is active
When the user clicks "Meus Favoritos" again
Then the table SHALL revert to showing all (or segment-filtered) FIIs

---

### Requirement: Favourite Toggle on FII Detail Page
The FII Detail page header SHALL include a star button that allows the user to add or remove
the current FII from their localStorage favourites.

#### Scenario: Adding a favourite from detail page
Given the user is on the HGLG11 detail page and HGLG11 is not yet favourited
When the user clicks the star icon in the header
Then HGLG11 SHALL be added to localStorage favourites
And the star icon SHALL change to filled state

## MODIFIED Requirements

### Requirement: Scanner Score Column
The scanner endpoint (`GET /api/scanner`) MUST use `calculate_fii_score()` instead of the
stock-metric `evaluate_company()` so that score reflects FII-specific quality dimensions.

#### Scenario: Scanner returns non-zero scores
Given fundamentals data is available for at least one FII in the universe
When `GET /api/scanner` is called
Then each FII in the response with available data SHALL have `score` greater than 0
