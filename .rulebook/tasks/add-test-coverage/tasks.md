## 1. Core Engine Tests
- [x] 1.1 Write tests for `core/fire_engine.py` → `tests/test_fire_engine.py`
- [x] 1.2 Write tests for `core/income_engine.py` → `tests/test_income_engine.py`
- [x] 1.3 Write tests for `core/decision_engine.py` → `tests/test_decision_engine.py`
- [x] 1.4 Write tests for `core/portfolio_engine.py` → `tests/test_portfolio_engine.py`
- [x] 1.5 Write tests for `core/position_engine.py` → `tests/test_position_engine.py`
- [x] 1.6 Write tests for `core/risk_engine.py` → `tests/test_risk_engine.py`
- [x] 1.7 Write tests for `core/macro_engine.py` → `tests/test_macro_engine.py`
- [x] 1.8 Write tests for `core/report_engine.py` → `tests/test_report_engine.py`
- [x] 1.9 Write tests for `core/quant_engine.py` → `tests/test_quant_engine.py`
- [x] 1.10 Write tests for `core/profile_allocator.py` → `tests/test_profile_allocator.py`
- [x] 1.11 Write tests for `core/class_rebalancer.py` → `tests/test_class_rebalancer.py`
- [x] 1.12 Write tests for `core/state_repository.py` → `tests/test_state_repository.py`
- [x] 1.13 Write tests for `core/security.py` → `tests/test_security.py`

## 2. Service Layer Tests
- [x] 2.1 Write tests for `services/simulador_service.py` → `tests/test_simulador_service.py`
- [x] 2.2 Write tests for `services/rebalance_engine.py` → `tests/test_rebalance_engine.py`
- [x] 2.3 Write tests for `services/explain_engine.py` → `tests/test_explain_engine.py`
- [x] 2.4 Write tests for `services/portfolio_service.py` → `tests/test_portfolio_service.py`

## 3. Data Layer Tests
- [x] 3.1 Write tests for `data/data_loader.py` → `tests/test_data_loader.py`
- [x] 3.2 Write tests for `data/data_bridge.py` → `tests/test_data_bridge.py`
- [x] 3.3 Write tests for `data/fundamentals_scraper.py` → `tests/test_fundamentals_scraper.py`
- [x] 3.4 Write tests for `data/cvm_b3_client.py` → `tests/test_cvm_b3_client.py`
- [x] 3.5 Write tests for `data/fundsexplorer_scraper.py` → `tests/test_fundsexplorer_scraper.py`

## 4. API / Infra / CLI Tests
- [x] 4.1 Write tests for `api/main.py` → `tests/test_api.py` (29 tests, all endpoints)
- [x] 4.2 Write tests for `infra/database.py` → `tests/test_database.py`
- [x] 4.3 Write tests for `scripts/alphacota_cli.py` → `tests/test_alphacota_cli.py` (22 tests)

## 5. Cleanup and Finalization
- [x] 5.1 Migrate useful manual scripts from `/scripts/` to `/tests/`
- [x] 5.2 Remove obsolete manual test scripts from `/scripts/`
- [x] 5.3 Update CI threshold from `--cov-fail-under=80` to `--cov-fail-under=95`
- [x] 5.4 Verify full test suite passes with 95%+ coverage (96.71%, 668 tests)
