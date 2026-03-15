# Vectorizer Indexing Specification

## Purpose
This specification defines the requirements for indexing the AlphaCota codebase into the Vectorizer system for semantic retrieval and GraphRAG.

## ADDED Requirements

### Requirement: Codebase Ingestion
The system SHALL traverse the `b:\alphacota` directory and ingest all relevant source code files (.py, .md, .txt) into the Vectorizer.

#### Scenario: Successful file ingestion
Given a collection named "alphacota" exists
When the indexing script is executed
Then all matching files are converted to vectors and stored with their relative paths as metadata
And the collection's vector count reflects the total number of ingested document chunks

### Requirement: Semantic Relationship Discovery
The system MUST trigger automatic relationship discovery between code entities within the indexed collection.

#### Scenario: Graph discovery activation
Given the ingestion of core modules is complete
When the `graph_discover_edges` tool is called
Then the system creates `SIMILAR_TO` or `REFERENCES` edges between semantically related chunks
And the graph status confirms the discovery progress
