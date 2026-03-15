## 1. Remove Orphaned Files
- [ ] 1.1 Delete `cota_ai/get-pip.py` (2.1MB binary, no purpose)
- [ ] 1.2 Delete runtime databases from repo (`alphacota.db`, `cota_ai/meus_investimentos.db`)
- [ ] 1.3 Add `*.db` pattern to `.gitignore` if not already covered

## 2. Evaluate Legacy Code
- [ ] 2.1 Audit `cota_ai/ai_service.py` for reusable AI integration code
- [ ] 2.2 Audit `cota_ai/news_scraper.py` for reusable news fetching code
- [ ] 2.3 Migrate useful code to `core/` or `services/` if applicable
- [ ] 2.4 Deprecate or archive `cota_ai/` directory

## 3. Scripts Cleanup
- [ ] 3.1 Identify obsolete manual test scripts in `/scripts/`
- [ ] 3.2 Remove scripts that duplicate formal tests in `/tests/`
- [ ] 3.3 Keep only utility scripts (indexing, deployment, validation)

## 4. Verification
- [ ] 4.1 Verify no broken imports reference removed files
- [ ] 4.2 Verify all tests still pass after cleanup
- [ ] 4.3 Verify `.gitignore` covers all runtime artifacts
