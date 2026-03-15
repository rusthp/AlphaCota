# Spec Delta: Modern Frontend

**Delta Type**: ADDED

## Purpose
Replace the monolithic Streamlit dashboard with a modern, componentized frontend application
that consumes the AlphaCota REST API. This enables better user experience, separation of
concerns between frontend and backend, and a professional interface based on the reference
design from alpha-cota-insight repository.

### Requirement: Frontend SHALL Consume REST API

The new frontend SHALL communicate exclusively with the FastAPI backend via REST endpoints.
No direct Python function calls or Streamlit-specific patterns SHALL be used.

#### Scenario: User views portfolio analysis
- Given a user navigating to the portfolio page
- When the frontend loads
- Then it fetches data from `GET /api/portfolio` endpoint
- And renders the portfolio overview with charts and metrics

### Requirement: API SHALL Expose All Dashboard Functionalities

The FastAPI backend SHALL expose REST endpoints for every feature currently available
in the Streamlit dashboard (backtest, stress testing, Markowitz, correlation, macro,
momentum, clustering, reports).

#### Scenario: All Streamlit features are accessible via API
- Given the expanded API
- When a client requests any analysis previously available in Streamlit
- Then the API returns the same data in JSON format
- And the response includes all metrics and chart data

### Requirement: Frontend MUST Achieve Feature Parity

The new frontend MUST implement all features present in the current Streamlit dashboard
before the Streamlit version is deprecated.

#### Scenario: Feature parity verification
- Given the new frontend and the existing Streamlit dashboard
- When both are compared feature by feature
- Then the new frontend supports all existing analysis types
- And report export (HTML tearsheet, CSV) is available
