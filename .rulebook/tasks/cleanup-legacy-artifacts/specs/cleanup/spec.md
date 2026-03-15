# Spec Delta: Legacy Cleanup

**Delta Type**: REMOVED

## Purpose
Remove orphaned files, runtime artifacts, and legacy prototype code from the repository
to reduce clone size, eliminate confusion, and maintain a clean project structure aligned
with the current architecture in core/, services/, and frontend/.

### Requirement: Repository SHALL NOT Contain Runtime Artifacts

The repository SHALL NOT contain SQLite database files, binary artifacts, or
generated files that are produced at runtime.

#### Scenario: Fresh clone contains no runtime data
- Given a fresh clone of the repository
- When the developer lists all files
- Then no `.db` files exist in the working tree
- And no binary installer scripts (get-pip.py) exist
- And `.gitignore` prevents accidental commits of runtime artifacts

### Requirement: Legacy Code MUST Be Evaluated Before Removal

Legacy code in `cota_ai/` MUST be audited for reusable components before
the directory is deprecated or removed.

#### Scenario: AI service code is evaluated for migration
- Given the `cota_ai/ai_service.py` module with Groq/Llama integration
- When the audit identifies reusable code
- Then useful functions are migrated to `core/` or `services/`
- And the legacy directory is marked as deprecated or removed
