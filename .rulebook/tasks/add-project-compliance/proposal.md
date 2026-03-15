# Proposal: Add Project Compliance

## Why
A validacao do projeto contra o Rulebook revelou 6 falhas estruturais que impedem conformidade
com os padroes definidos em AGENTS.md e PYTHON.md. O projeto nao possui `/docs/`, `.env.example`,
`pyproject.toml`, nem `requirements-dev.txt`. O README esta desatualizado (documenta apenas o
prototipo original) e o mypy nao e bloqueante no CI.

## What Changes
- Criar diretorio `/docs/` com documentacao da arquitetura do projeto.
- Criar `.env.example` com template de variaveis de ambiente necessarias.
- Criar `pyproject.toml` com configuracoes de ruff, mypy, pytest e black.
- Criar `requirements-dev.txt` com dependencias de desenvolvimento.
- Atualizar `README.md` refletindo a arquitetura atual (core/, services/, data/, frontend/).
- Tornar mypy bloqueante no CI (remover `continue-on-error: true`).

## Impact
- Affected specs: `project/spec.md` (New)
- Affected code: `pyproject.toml`, `requirements-dev.txt`, `.env.example`, `README.md`, `docs/`, `.github/workflows/python-lint.yml`
- Breaking change: NO
- User benefit: Onboarding mais rapido, qualidade de codigo enforced, documentacao acessivel.
