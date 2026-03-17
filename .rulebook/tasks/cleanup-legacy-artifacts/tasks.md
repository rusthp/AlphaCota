## 1. Remove Orphaned Files
- [x] 1.1 Delete `cota_ai/get-pip.py` (2.1MB binary, no purpose)
- [x] 1.2 Delete runtime databases from repo (`alphacota.db` untracked via git rm --cached)
- [x] 1.3 Add `*.db` pattern to `.gitignore`

## 2. Evaluate Legacy Code
- [x] 2.1 Audit `cota_ai/ai_service.py` — migrated to `core/ai_engine.py`
- [x] 2.2 Audit `cota_ai/news_scraper.py` — migrated to `data/news_scraper.py`
- [x] 2.3 Migrate useful code to `core/` and `data/`
- [x] 2.4 Verified no active imports from `cota_ai/` — directory deprecated

## 3. Scripts Cleanup
- [x] 3.1 Identified 20 obsolete manual test scripts in `/scripts/`
- [x] 3.2 Removed all manual test scripts (duplicated by formal tests)
- [x] 3.3 Kept utility scripts: `alphacota_cli.py`, `bootstrap_data.py`
- [x] 3.4 Fixed broken import in `alphacota_cli.py`

## 4. Verification
- [x] 4.1 Verified no broken imports reference removed files
- [x] 4.2 Verify all tests still pass after cleanup (581 passed)
- [x] 4.3 Verified `.gitignore` covers all runtime artifacts
