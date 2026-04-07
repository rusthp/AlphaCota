"""
data/vectorizer_client.py

Cliente HTTP para o Vectorizer (busca semântica no codebase e dados).
Permite que o AI engine e outros módulos consultem o vectorizer
como base de conhecimento.

Uso:
    from data.vectorizer_client import VectorizerClient

    client = VectorizerClient()
    results = client.search("como calcular dividend yield")
"""

import os
from typing import Optional

try:
    import requests

    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from core.logger import logger

# Defaults (podem ser sobrescritos via env vars)
VECTORIZER_URL = os.getenv("VECTORIZER_URL", "http://localhost:15002")
VECTORIZER_USER = os.getenv("VECTORIZER_USER", "root")
VECTORIZER_PASS = os.getenv("VECTORIZER_PASS", "76m30JRY92Ie")
DEFAULT_COLLECTION = os.getenv("VECTORIZER_COLLECTION", "semantic_code")


class VectorizerClient:
    """Cliente para o Vectorizer — busca semântica via REST API."""

    def __init__(
        self,
        base_url: str = VECTORIZER_URL,
        username: str = VECTORIZER_USER,
        password: str = VECTORIZER_PASS,
        collection: str = DEFAULT_COLLECTION,
    ):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.collection = collection
        self._token: Optional[str] = None

    def _authenticate(self) -> bool:
        """Obtém JWT token do vectorizer."""
        if not HAS_REQUESTS:
            logger.warning("requests não instalado — vectorizer indisponível")
            return False
        try:
            resp = requests.post(
                f"{self.base_url}/auth/login",
                json={"username": self.username, "password": self.password},
                timeout=5,
            )
            if resp.status_code == 200:
                self._token = resp.json().get("access_token")
                return True
            logger.warning("Vectorizer auth falhou: %s", resp.status_code)
            return False
        except Exception as e:
            logger.warning("Vectorizer inacessível: %s", e)
            return False

    def _headers(self) -> dict:
        """Retorna headers com Bearer token."""
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    def _ensure_auth(self) -> bool:
        """Garante autenticação válida."""
        if self._token:
            return True
        return self._authenticate()

    def health(self) -> dict:
        """Verifica saúde do vectorizer."""
        if not HAS_REQUESTS:
            return {"status": "unavailable", "reason": "requests not installed"}
        try:
            resp = requests.get(f"{self.base_url}/health", timeout=3)
            return resp.json()
        except Exception as e:
            return {"status": "unavailable", "reason": str(e)}

    def search(
        self,
        query: str,
        limit: int = 5,
        collection: Optional[str] = None,
    ) -> list[dict]:
        """Busca semântica por texto no vectorizer.

        Args:
            query: Texto de busca (linguagem natural ou código).
            limit: Número máximo de resultados.
            collection: Nome da collection (default: semantic_code).

        Returns:
            Lista de dicts com keys: id, score, content, file_path, metadata.
        """
        if not HAS_REQUESTS or not self._ensure_auth():
            return []

        col = collection or self.collection
        try:
            resp = requests.post(
                f"{self.base_url}/collections/{col}/search/text",
                json={"query": query, "limit": limit},
                headers=self._headers(),
                timeout=10,
            )
            if resp.status_code == 401:
                # Token expirado, re-autenticar
                self._token = None
                if not self._authenticate():
                    return []
                resp = requests.post(
                    f"{self.base_url}/collections/{col}/search/text",
                    json={"query": query, "limit": limit},
                    headers=self._headers(),
                    timeout=10,
                )

            if resp.status_code != 200:
                logger.warning("Vectorizer search falhou: %s", resp.status_code)
                return []

            data = resp.json()
            results = []
            for hit in data.get("results", []):
                payload = hit.get("payload", {})
                results.append(
                    {
                        "id": hit.get("id"),
                        "score": hit.get("score", 0),
                        "content": payload.get("content", ""),
                        "file_path": payload.get("file_path", ""),
                        "metadata": payload.get("metadata", {}),
                    }
                )
            return results

        except Exception as e:
            logger.warning("Vectorizer search error: %s", e)
            return []

    def list_collections(self) -> list[dict]:
        """Lista todas as collections disponíveis."""
        if not HAS_REQUESTS or not self._ensure_auth():
            return []
        try:
            resp = requests.get(
                f"{self.base_url}/collections",
                headers=self._headers(),
                timeout=5,
            )
            if resp.status_code == 200:
                return resp.json().get("collections", [])
            return []
        except Exception:
            return []

    def get_context_for_query(self, query: str, limit: int = 5) -> str:
        """Busca contexto relevante e retorna como texto formatado.

        Útil para injetar no prompt do AI engine como RAG (Retrieval Augmented Generation).

        Args:
            query: Pergunta ou tópico.
            limit: Máximo de trechos.

        Returns:
            String formatada com os trechos mais relevantes do codebase.
        """
        results = self.search(query, limit=limit)
        if not results:
            return ""

        parts = []
        for i, r in enumerate(results, 1):
            path = r.get("file_path", "desconhecido")
            content = r.get("content", "").strip()
            if content:
                parts.append(f"[{i}] {path}\n{content}")

        return "\n\n---\n\n".join(parts)
