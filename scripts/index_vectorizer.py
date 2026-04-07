"""
AlphaCota Vectorizer Indexer
----------------------------
Indexes all AlphaCota source files into the 'alphacota' vectorizer collection.

Usage:
    python scripts/index_vectorizer.py           # index all files
    python scripts/index_vectorizer.py --dry-run # preview only
    python scripts/index_vectorizer.py --reset   # drop + re-index
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import requests

# ── Config ────────────────────────────────────────────────────────────────────

VECTORIZER_URL = "http://localhost:15002/mcp"
API_KEY = "kwdt6ZoqRvgyp3J3tVImhSpytGNSnYtt"
COLLECTION = "alphacota"
ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {
    ".git", ".venv", ".venv-ruff", "__pycache__", "node_modules",
    ".pytest_cache", "htmlcov", "dist", "build", ".agent", ".claude",
    ".rulebook", "data/historical_prices", "data/historical_dividends",
    "frontend/src/components/ui",  # generated shadcn components
}

INCLUDE_EXTENSIONS = {".py", ".ts", ".tsx", ".md", ".toml", ".yml", ".yaml"}

INCLUDE_ROOTS = {
    "core", "data", "api", "services", "frontend/src", "tests",
    "alphacota_mcp", "infra",
    "cli.py", "start.py", "CLAUDE.md", "README.md",
    "pyproject.toml", "requirements.txt",
}

MAX_FILE_SIZE_KB = 120

# ── MCP session ───────────────────────────────────────────────────────────────

class VectorizerSession:
    def __init__(self) -> None:
        self.session_id: str | None = None
        self._req_id = 0

    def _headers(self) -> dict:
        h = {
            "x-api-key": API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            h["Mcp-Session-Id"] = self.session_id
        return h

    def _post(self, payload: dict, timeout: int = 20) -> dict:
        resp = requests.post(
            VECTORIZER_URL,
            json=payload,
            headers=self._headers(),
            timeout=timeout,
        )
        resp.raise_for_status()
        # Response is SSE: "data: {...}\n\nid: 0/0"
        for line in resp.text.splitlines():
            if line.startswith("data: "):
                return json.loads(line[6:])
        return {}

    def connect(self) -> None:
        """Initialize MCP session."""
        self._req_id += 1
        resp = requests.post(
            VECTORIZER_URL,
            json={
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "alphacota-indexer", "version": "1.0"},
                },
                "id": self._req_id,
            },
            headers=self._headers(),
            timeout=15,
        )
        resp.raise_for_status()
        self.session_id = (
            resp.headers.get("Mcp-Session-Id")
            or resp.headers.get("mcp-session-id")
        )
        # Send initialized notification
        requests.post(
            VECTORIZER_URL,
            json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            headers=self._headers(),
            timeout=10,
        )

    def call(self, tool: str, args: dict) -> dict:
        self._req_id += 1
        result = self._post({
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": tool, "arguments": args},
            "id": self._req_id,
        })
        if result.get("error"):
            raise RuntimeError(f"MCP error: {result['error']}")
        content = result.get("result", {}).get("content", [{}])
        return json.loads(content[0].get("text", "{}")) if content else {}

    def insert(self, text: str, metadata: dict) -> str:
        r = self.call("insert_text", {
            "collection_name": COLLECTION,
            "text": text,
            "metadata": metadata,
        })
        return r.get("vector_id", "?")


# ── File collection ────────────────────────────────────────────────────────────

def _lang(ext: str) -> str:
    return {
        ".py": "python", ".ts": "typescript", ".tsx": "typescript",
        ".md": "markdown", ".toml": "toml", ".yml": "yaml", ".yaml": "yaml",
    }.get(ext, "text")


def _should_skip(path: Path) -> bool:
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    return any(
        rel == d or rel.startswith(d + "/")
        for d in SKIP_DIRS
    )


def collect_files() -> list[Path]:
    files: list[Path] = []

    def _walk(p: Path) -> None:
        if _should_skip(p):
            return
        if p.is_file() and p.suffix in INCLUDE_EXTENSIONS:
            files.append(p)
        elif p.is_dir():
            for child in sorted(p.iterdir()):
                _walk(child)

    for entry in INCLUDE_ROOTS:
        _walk(ROOT / entry)

    return files


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Index AlphaCota into vectorizer")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reset", action="store_true", help="Delete and re-index")
    args = parser.parse_args()

    files = collect_files()
    print(f"Found {len(files)} files to index into '{COLLECTION}'\n")

    if args.dry_run:
        for f in files:
            print(f"  {f.relative_to(ROOT)}")
        print(f"\nDRY RUN: {len(files)} files would be indexed")
        return

    session = VectorizerSession()
    session.connect()
    print(f"MCP session: {session.session_id}\n")

    if args.reset:
        print("Resetting collection...")
        try:
            session.call("delete_collection", {"name": COLLECTION})
        except Exception:
            pass
        session.call("create_collection", {
            "name": COLLECTION, "dimension": 512,
            "metric": "cosine", "graph": {"enabled": True},
        })
        print("Collection recreated.\n")

    ok = skip = err = 0
    for i, f in enumerate(files, 1):
        rel = f.relative_to(ROOT)

        if f.stat().st_size > MAX_FILE_SIZE_KB * 1024:
            print(f"[{i}/{len(files)}] SKIP (too large): {rel}")
            skip += 1
            continue

        content = f.read_text(encoding="utf-8", errors="ignore").strip()
        if not content:
            print(f"[{i}/{len(files)}] SKIP (empty): {rel}")
            skip += 1
            continue

        try:
            session.insert(
                text=f"# File: {str(rel).replace(chr(92), '/')}\n\n{content}",
                metadata={
                    "file_path": str(rel).replace("\\", "/"),
                    "file_extension": f.suffix.lstrip("."),
                    "language": _lang(f.suffix),
                    "source": "alphacota",
                },
            )
            print(f"[{i}/{len(files)}] OK: {rel}")
            ok += 1
        except Exception as e:
            print(f"[{i}/{len(files)}] ERROR: {rel} — {e}")
            err += 1

        if i % 15 == 0:
            time.sleep(0.3)

    print(f"\nDone: {ok} indexed, {skip} skipped, {err} errors")


if __name__ == "__main__":
    main()
