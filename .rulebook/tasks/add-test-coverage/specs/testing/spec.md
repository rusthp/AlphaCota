# Spec Delta: Test Coverage

**Delta Type**: ADDED

## Purpose
Achieve and enforce 95% test coverage across all Python modules in the AlphaCota project,
ensuring reliability of quantitative engines, service orchestration, data layer, and API
endpoints through comprehensive automated testing.

### Requirement: All Core Modules SHALL Have Unit Tests

Every Python module in `core/` SHALL have a corresponding test file in `tests/` with
complete assertions covering normal paths, edge cases, and error paths.

#### Scenario: Core engine produces correct calculations
- Given a core engine module (e.g., fire_engine, income_engine, risk_engine)
- When unit tests are executed via pytest
- Then all mathematical calculations are verified against known expected values
- And edge cases (zero values, negative inputs, empty data) are tested
- And error paths raise appropriate exceptions

### Requirement: Service and Data Layers SHALL Have Integration Tests

All service modules in `services/` and data modules in `data/` SHALL have tests
that verify correct orchestration and data flow.

#### Scenario: Service layer orchestrates engines correctly
- Given a service module (e.g., simulador_service, allocation_pipeline)
- When integration tests run with mocked data sources
- Then the service correctly calls underlying engines
- And results are properly aggregated and returned

### Requirement: CI Coverage Gate MUST Enforce 95% Minimum

The CI pipeline MUST fail if test coverage drops below 95%.

#### Scenario: Coverage drops below threshold
- Given a pull request that reduces test coverage below 95%
- When the CI test workflow runs
- Then pytest fails with `--cov-fail-under=95`
- And the pull request is blocked from merging
