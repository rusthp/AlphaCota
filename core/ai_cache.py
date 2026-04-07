"""
core/ai_cache.py

Cache local em SQLite para as análises do Groq/Llama.
As análises demoram e gastam a mesma (ou muita) quota na API do Groq,
por isso fazemos cache local via banco SQL.
O TTL de validade adotado é de 6 horas para as respostas cacheadas.
"""
import sqlite3
import datetime
import json
import os
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sentiments_cache.db")

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sentiment_cache (
                ticker TEXT PRIMARY KEY,
                sentiment_score REAL,
                raw_response TEXT,
                news_count INTEGER,
                created_at TIMESTAMP
            )
        """)
        conn.commit()

# Cache init
init_db()


def get_cached_sentiment(ticker: str, ttl_hours: int = 6) -> dict | None:
    """Busca um sentimento no cache se não estiver expirado."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT sentiment_score, raw_response, news_count, created_at FROM sentiment_cache WHERE ticker = ?",
            (ticker.upper(),)
        )
        row = cursor.fetchone()
        if not row:
            return None

        sentiment_score, raw_response, news_count, created_at_str = row
        created_at = datetime.datetime.fromisoformat(created_at_str)
        now = datetime.datetime.now()

        # Checa TTL
        if (now - created_at).total_seconds() > (ttl_hours * 3600):
            return None

        return {
            "success": True,
            "ticker": ticker.upper(),
            "sentiment_score": sentiment_score,
            "raw_response": raw_response,
            "news_count": news_count,
            "cached": True
        }

def save_cached_sentiment(data: dict):
    """Salva análises do Groq no cache SQLite."""
    if not data.get("success") or not data.get("ticker"):
        return

    ticker = data["ticker"].upper()
    score = data.get("sentiment_score", 0.0)
    raw = data.get("raw_response", "")
    nc = data.get("news_count", 0)
    now_str = datetime.datetime.now().isoformat()

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sentiment_cache (ticker, sentiment_score, raw_response, news_count, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                sentiment_score=excluded.sentiment_score,
                raw_response=excluded.raw_response,
                news_count=excluded.news_count,
                created_at=excluded.created_at
        """, (ticker, score, raw, nc, now_str))
        conn.commit()
