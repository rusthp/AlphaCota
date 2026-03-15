# Proposal: Cleanup Legacy Artifacts

## Why
O projeto contem artefatos legados que aumentam o tamanho do repositorio, geram confusao
na estrutura e violam regras de qualidade do Rulebook. O arquivo `cota_ai/get-pip.py` (2.1MB)
e um binario orfao. Databases SQLite de runtime (`alphacota.db`, `meus_investimentos.db`)
estao commitados no repo. O diretorio `cota_ai/` contem o prototipo original que foi
superado pelo sistema atual em `core/`, `services/` e `frontend/`.

## What Changes
- Remover `cota_ai/get-pip.py` (arquivo orfao de 2.1MB).
- Remover databases de runtime do repo e adicionar ao `.gitignore`.
- Avaliar e deprecar o diretorio `cota_ai/` (mover AI service para integracao no core se necessario).
- Limpar scripts manuais obsoletos em `/scripts/`.

## Impact
- Affected specs: `cleanup/spec.md` (New)
- Affected code: `cota_ai/`, `.gitignore`, `scripts/`
- Breaking change: NO
- User benefit: Repositorio mais limpo, menor tamanho de clone, estrutura clara.
