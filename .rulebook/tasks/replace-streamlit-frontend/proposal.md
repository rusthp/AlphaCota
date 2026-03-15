# Proposal: Replace Streamlit with Modern Frontend

## Why
O dashboard atual e um unico arquivo Streamlit de 64KB (`frontend/dashboard.py`) que contem
toda a logica de UI em um monolito Python. O usuario deseja substituir por um frontend moderno
baseado no modelo de referencia `git@github.com:rusthp/alpha-cota-insight.git`, que oferece
melhor UX, componentizacao e separacao de responsabilidades.

## What Changes
- Clonar e analisar o repositorio de referencia `alpha-cota-insight.git`.
- Projetar a arquitetura do novo frontend (React/Next.js ou framework identificado no repo de referencia).
- Expandir a FastAPI (`api/main.py`) com endpoints completos para todas as funcionalidades do dashboard.
- Implementar o frontend consumindo a API REST.
- Deprecar `frontend/dashboard.py` (Streamlit).

## Impact
- Affected specs: `frontend/spec.md` (New)
- Affected code: `frontend/` (rewrite), `api/main.py` (expand), `frontend/dashboard.py` (deprecate)
- Breaking change: YES (UI completamente substituida)
- User benefit: UX moderna, melhor performance, componentizacao, separacao frontend/backend.
