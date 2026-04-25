<!-- OVERRIDE:START -->
# Project-Specific Overrides

Add your custom rules and team conventions here.
This file is never overwritten by `rulebook init` or `rulebook update`.

<!-- MIGRATED-FROM-CLAUDE-MD on 2026-04-08T18:19:47.298Z by rulebook v5.3.0 -->
<!-- The following directives were extracted from your previous CLAUDE.md. -->
<!-- They are now imported by the new CLAUDE.md via @AGENTS.override.md, so -->
<!-- Claude Code re-loads them at session start exactly as before. -->
<!-- Review and prune as needed — rulebook will never touch this section. -->

# CLAUDE.md (legacy v5.2 content, preserved by rulebook v5.3.0)

# CLAUDE.md

@.rulebook/COMPACT_CONTEXT.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

This project uses @hivehub/rulebook standards. All code generation should follow the rules defined in AGENTS.md.

**Languages**: Python
**Coverage Threshold**: 95%

## ⚠️ CRITICAL: File Editing Rules

**MANDATORY**: When editing multiple files, you MUST edit files **SEQUENTIALLY**, one at a time.

### Why Sequential Editing is Required

The Edit tool uses exact string matching for replacements. When multiple files are edited in parallel:
- The tool may fail to find the exact string in some files
- Race conditions can cause partial or corrupted edits
- Error recovery becomes impossible

### Correct Pattern

```
✅ CORRECT (Sequential):
1. Edit file A → Wait for confirmation
2. Edit file B → Wait for confirmation
3. Edit file C → Wait for confirmation

❌ WRONG (Parallel):
1. Edit files A, B, C simultaneously → Failures likely
```

### Implementation Rules

1. **NEVER call multiple Edit tools in parallel** for different files
2. **ALWAYS wait for each edit to complete** before starting the next
3. **Verify each edit succeeded** before proceeding
4. **If an edit fails**, retry that specific edit before moving on

## ⚠️ CRITICAL: Test Implementation Rules

**MANDATORY**: You MUST write **complete, production-quality tests**. Never simplify or reduce test coverage.

### Forbidden Test Patterns

```typescript
// ❌ NEVER do this - placeholder tests
it('should work', () => {
  expect(true).toBe(true);
});

// ❌ NEVER do this - skipped tests
it.skip('should handle edge case', () => {});

// ❌ NEVER do this - incomplete assertions
it('should return data', () => {
  const result = getData();
  expect(result).toBeDefined(); // Too weak!
});

// ❌ NEVER do this - "simplify" by removing test cases
// Original had 10 test cases, don't reduce to 3
```

### Required Test Patterns

```typescript
// ✅ CORRECT - complete test with proper assertions
it('should return user data with correct structure', () => {
  const result = getUserById(1);
  expect(result).toEqual({
    id: 1,
    name: 'John Doe',
    email: 'john@example.com',
    createdAt: expect.any(Date),
  });
});

// ✅ CORRECT - test edge cases and error paths
it('should throw NotFoundError when user does not exist', () => {
  expect(() => getUserById(999)).toThrow(NotFoundError);
});
```

### Test Implementation Rules

1. **NEVER simplify tests** - Implement the full, complete test as originally designed
2. **NEVER skip test cases** - Every test case in the spec must be implemented
3. **NEVER use placeholder assertions** - Each assertion must verify actual behavior
4. **ALWAYS test error paths** - Exceptions, edge cases, and failure modes
5. **ALWAYS maintain coverage** - Tests must achieve the project's coverage threshold (95%+)

## Critical Rules

1. **ALWAYS read AGENTS.md first** - Contains all project standards and patterns
2. **Edit files sequentially** - One at a time, verify each edit
3. **Write complete tests** - No placeholders, no simplifications
4. **Tests required** - Minimum 95% coverage for all new code
5. **Quality checks before committing**:
   - Type check / Compiler check
   - Lint (zero warnings)
   - All tests passing
   - Coverage threshold met
6. **Documentation** - Update /docs/ when implementing features

## Persistent Memory

This project uses a **persistent memory system** via the Rulebook MCP server.
Memory persists across sessions — use it to maintain context between conversations.

**MANDATORY: You MUST actively use memory to preserve context across sessions.**

### Auto-Capture

Tool interactions (task create/update/archive, skill enable/disable) are auto-captured.
But you MUST also manually save important context:

- **Architectural decisions** — why you chose one approach over another
- **Bug fixes** — root cause and resolution
- **Discoveries** — codebase patterns, gotchas, constraints
- **Feature implementations** — what was built, key design choices
- **User preferences** — coding style, conventions, workflow preferences
- **Session summaries** — what was accomplished, what's pending

### Memory Commands (MCP)

```
rulebook_memory_save    — Save context (type, title, content, tags)
rulebook_memory_search  — Search past context (query, mode: hybrid/bm25/vector)
rulebook_memory_get     — Get full details by ID
rulebook_memory_timeline — Chronological context around a memory
rulebook_memory_stats   — Database stats
rulebook_memory_cleanup — Evict old memories
```

### Session Workflow

1. **Start of session**: `rulebook_memory_search` for relevant past context
2. **During work**: Save decisions, bugs, discoveries as they happen
3. **End of session**: Save a summary with `type: observation`

## Commands

```bash
# Quality checks
npm run type-check    # TypeScript type checking
npm run lint          # Run linter
npm test              # Run tests
npm run build         # Build project

# Task management (if using Rulebook)
rulebook task list    # List tasks
rulebook task show    # Show task details
rulebook validate     # Validate project structure
```

## File Structure

- `AGENTS.md` - Main project standards and AI directives (auto-generated by rulebook)
- `.rulebook/` - Modular rule definitions and task specs
- `/docs/` - Project documentation
- `/tests/` - Test files

When in doubt, check AGENTS.md for guidance.

## Vectorizer — Busca Semântica no Código

O projeto AlphaCota está indexado na collection **`alphacota`** do vectorizer local (`http://localhost:15002`).

### Quando USAR o vectorizer (economiza tokens)

| Situação | Query exemplo |
|----------|--------------|
| Entender como uma função funciona | `"como funciona o cálculo do Sharpe"` |
| Encontrar onde algo está implementado | `"onde está o score_engine dividend yield"` |
| Ver padrões de uso de um módulo | `"exemplos de uso do markowitz_engine"` |
| Descobrir quais arquivos tocam uma feature | `"endpoints da API de portfolio"` |
| Entender testes existentes antes de escrever novos | `"testes do fundamentals_scraper mock HTTP"` |

### Quando NÃO usar (use Read/Grep direto)

- Você já sabe o caminho exato do arquivo → use `Read`
- Busca por string literal exata → use `Grep`
- Edição cirúrgica em arquivo conhecido → use `Edit` direto
- Arquivo pequeno e bem definido → use `Read`

### Como buscar

```
# Busca semântica (conceitos, comportamentos)
mcp__vectorizer__search_semantic  collection=alphacota  query="..."

# Busca híbrida (semântica + palavras-chave) — padrão recomendado
mcp__vectorizer__search_hybrid  collection=alphacota  query="..."

# Busca em múltiplas collections
mcp__vectorizer__multi_collection_search  collections=["alphacota"]  query="..."
```

### Fluxo obrigatório para tarefas de implementação

```
1. SEMPRE buscar no vectorizer ANTES de ler arquivos:
   → search_hybrid("o que preciso entender sobre X")

2. Se o resultado for suficiente → implementar direto (economiza tokens)

3. Se precisar de detalhes → Read só os arquivos específicos retornados

4. NUNCA ler toda a pasta com glob quando vectorizer pode responder
```

### Re-indexar após mudanças

```bash
# Após implementar novas features ou refatorar:
python scripts/index_vectorizer.py --reset
```

---

## Agent System — Two Layers

This project uses **two distinct agent systems**. Do not confuse them.

### Layer 1 — `.agent/` (Antigravity Kit — Generic Framework)

Generic, reusable agent definitions compatible with **any AI tool** (Claude Code, Gemini, Cursor, etc.).

```
.agent/
├── agents/        # 20 specialist agents (orchestrator, backend-specialist, etc.)
├── skills/        # 48 domain knowledge modules (python-patterns, api-patterns, etc.)
├── workflows/     # 11 slash command procedures (/plan, /debug, /deploy, etc.)
├── rules/
│   ├── GEMINI.md  # Gemini-specific rules
│   └── PYTHON.md  # Python coding rules for all IAs (pure functions, type hints)
└── ARCHITECTURE.md
```

**Use when**: Running a generic task not specific to AlphaCota (e.g., invoking `backend-specialist` for a generic Python pattern question).

### Layer 2 — `.claude/` (Claude Code Native — AlphaCota Specific)

Claude Code's native configuration. These agents run directly in Claude Code sessions.

```
.claude/
├── agents/
│   ├── alphacota-orchestrator.md   ← Master coordinator (knows Phases 1-6)
│   ├── alphacota-data-engineer.md  ← Phase 3: scrapers, data pipeline
│   ├── alphacota-quant-engineer.md ← Phase 4/5: quant engines
│   ├── alphacota-fullstack.md      ← FastAPI + React 18
│   ├── alphacota-qa.md             ← 95% pytest coverage enforcer
│   └── [18 generic Claude agents]  ← researcher, implementer, tester, etc.
├── commands/      # 14 rulebook slash commands
└── skills/        # 14 skill shortcuts
```

**Use when**: Working on AlphaCota features. Always prefer `alphacota-*` agents over generic ones for project tasks.

### Which Agent to Use

| Task | Agent |
|------|-------|
| Coordinating a multi-phase feature | `alphacota-orchestrator` |
| Data scrapers, data_loader, universe | `alphacota-data-engineer` |
| Score engine, backtest, markowitz | `alphacota-quant-engineer` |
| FastAPI endpoint or React component | `alphacota-fullstack` |
| Writing or fixing pytest tests | `alphacota-qa` |
| Generic exploration / research | `researcher` |
| Generic implementation | `implementer` |

<!-- END MIGRATED-FROM-CLAUDE-MD -->

<!-- OVERRIDE:END -->
