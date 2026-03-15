# Proposal: Index AlphaCota to Vectorizer

## Why
This task is necessary to enable semantic code search and intelligent exploration of the AlphaCota project. By indexing the codebase into Vectorizer, we can leverage GraphRAG and semantic retrieval for better development context and automated analysis.

## What Changes
- Implement a specialized indexing script in `b:\alphacota\scripts\index_to_vectorizer.py`.
- Create a new collection named `alphacota` in Vectorizer.
- Perform a complete ingestion of the project's core modules.
- Enable and trigger graph relationship discovery between indexed files.

## Impact
- Affected specs: `vectorizer/spec.md` (New)
- Affected code: `b:\alphacota\scripts\index_to_vectorizer.py`
- Breaking change: NO
- User benefit: Faster codebase exploration and semantic understanding for AI agents.
