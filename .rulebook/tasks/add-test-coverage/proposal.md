# Proposal: Add Test Coverage to 95%

## Why
O Rulebook exige 95% de cobertura de testes. Atualmente, apenas 7 modulos possuem testes formais
em `/tests/` (backtest, correlation, markowitz, momentum/cluster, stress, pipeline integration,
smart_aporte). Aproximadamente 20 modulos em core/, services/, data/, api/, infra/ e cli nao
possuem testes automatizados, resultando em cobertura muito abaixo do threshold.

## What Changes
- Escrever testes unitarios para ~15 modulos em `core/` sem cobertura.
- Escrever testes unitarios para ~4 modulos em `services/`.
- Escrever testes unitarios para ~3 modulos em `data/`.
- Escrever testes para `api/main.py`, `infra/database.py` e `cli.py`.
- Migrar scripts manuais uteis de `/scripts/` para `/tests/`.
- Remover scripts manuais obsoletos.
- Atualizar CI threshold de 80% para 95%.

## Impact
- Affected specs: `testing/spec.md` (New)
- Affected code: `tests/` (new test files), `.github/workflows/python-test.yml`, `scripts/`
- Breaking change: NO
- User benefit: Confianca na qualidade do codigo, prevencao de regressoes, CI robusto.
