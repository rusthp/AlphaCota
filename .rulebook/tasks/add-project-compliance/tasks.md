## 1. Configuration Phase
- [x] 1.1 Create `pyproject.toml` with ruff, mypy, pytest, black configurations
- [x] 1.2 Create `requirements-dev.txt` with dev dependencies (pytest, pytest-cov, ruff, mypy, black)
- [x] 1.3 Create `.env.example` with required environment variables template

## 2. Documentation Phase
- [x] 2.1 Create `/docs/architecture.md` with system architecture overview
- [x] 2.2 Create `/docs/modules.md` with module reference documentation
- [x] 2.3 Update `README.md` reflecting current architecture (core/, services/, data/, API, CLI)

## 3. CI Hardening Phase
- [x] 3.1 Make mypy blocking in `.github/workflows/python-lint.yml` (remove continue-on-error)
- [x] 3.2 Verify all CI workflows pass with new configurations

## 4. Verification Phase
- [x] 4.1 Run `ruff check .` with new pyproject.toml config — zero warnings (excluded .agent/, .venv-ruff/, cota_ai/ in pyproject.toml)
- [x] 4.2 Run `black --check .` — passes (73 files reformatted, 721 tests still pass)
- [x] 4.3 Verify `/docs/` directory exists with minimum documentation
