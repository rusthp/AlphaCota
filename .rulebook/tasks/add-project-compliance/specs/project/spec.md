# Spec Delta: Project Compliance

**Delta Type**: ADDED

## Purpose
Establish project-level configuration and documentation standards to ensure compliance with
Rulebook PYTHON.md and AGENTS.md requirements. This enables consistent tooling, easier onboarding,
and enforced code quality gates across the development workflow.

### Requirement: Project Configuration Files SHALL Exist

The project SHALL have a `pyproject.toml` file configuring ruff, mypy, pytest, and black.
The project SHALL have a `requirements-dev.txt` listing all development dependencies.
The project SHALL have a `.env.example` documenting required environment variables.

#### Scenario: Developer clones project and sets up environment
- Given a fresh clone of the repository
- When the developer runs `pip install -r requirements-dev.txt`
- Then all development tools (pytest, ruff, mypy, black) are available
- And `pyproject.toml` provides consistent configuration for all tools

### Requirement: Project Documentation SHALL Be Maintained in /docs/

The project SHALL maintain architecture documentation in `/docs/architecture.md`.
The project SHALL maintain module reference in `/docs/modules.md`.
The `README.md` SHALL reflect the current project architecture.

#### Scenario: New contributor reads project documentation
- Given a new contributor accessing the repository
- When they read `README.md` and `/docs/`
- Then they understand the system architecture, module structure, and how to run the project

### Requirement: CI Type Checking MUST Be Blocking

The mypy type checker in CI MUST fail the pipeline on type errors (no `continue-on-error`).

#### Scenario: Type error introduced in pull request
- Given a pull request with a type annotation error
- When the CI lint workflow runs
- Then the mypy step fails and blocks the merge
