import sqlite3
import json
import os
from pathlib import Path
from datetime import datetime

# Build DB path relative to the api directory
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "snapshots.db"

def get_connection():
    os.makedirs(DB_PATH.parent, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def create_tables():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS score_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                date TEXT NOT NULL,
                score_total REAL,
                details_json TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sentiment_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                date TEXT NOT NULL,
                sentiment TEXT,
                reason TEXT
            )
        ''')
        # Create indexes for fast retrieval
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_score_ticker ON score_history (ticker)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sentiment_ticker ON sentiment_history (ticker)')
        conn.commit()

# Run once on import to guarantee tables exist
create_tables()

def save_score_snapshot(ticker: str, score: float, details: dict, date_str: str = None):
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO score_history (ticker, date, score_total, details_json)
            VALUES (?, ?, ?, ?)
        ''', (ticker, date_str, score, json.dumps(details)))
        conn.commit()

def get_score_timeline(ticker: str, limit: int = 12):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT date, score_total, details_json 
            FROM score_history 
            WHERE ticker = ? 
            ORDER BY date ASC
            LIMIT ?
        ''', (ticker, limit))
        rows = cursor.fetchall()
        
    result = []
    for row in rows:
        result.append({
            "date": row["date"],
            "score": row["score_total"],
            "details": json.loads(row["details_json"]) if row["details_json"] else {}
        })
    return result

def save_sentiment_snapshot(ticker: str, sentiment: str, reason: str, date_str: str = None):
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO sentiment_history (ticker, date, sentiment, reason)
            VALUES (?, ?, ?, ?)
        ''', (ticker, date_str, sentiment, reason))
        conn.commit()

def get_sentiment_trend(ticker: str, limit: int = 5):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT date, sentiment, reason 
            FROM sentiment_history 
            WHERE ticker = ? 
            ORDER BY date DESC
            LIMIT ?
        ''', (ticker, limit))
        rows = cursor.fetchall()

    result = []
    # Reverse to return sorted by date ASC
    for row in rows:
        result.append({
            "date": row["date"],
            "sentiment": row["sentiment"],
            "reason": row["reason"]
        })
    return result[::-1]

def get_score_alerts(tickers: list[str], drop_threshold: float = 10.0):
    """
    Verifica para cada ticker se houve uma queda de score agressiva
    avaliando o último snapshot contra o penúltimo.
    Retorna uma lista de alertas.
    """
    alerts = []
    with get_connection() as conn:
        cursor = conn.cursor()
        for ticker in tickers:
            cursor.execute('''
                SELECT date, score_total 
                FROM score_history 
                WHERE ticker = ? 
                ORDER BY date DESC
                LIMIT 2
            ''', (ticker,))
            rows = cursor.fetchall()
            if len(rows) == 2:
                latest = rows[0]["score_total"]
                previous = rows[1]["score_total"]
                drop = previous - latest
                if drop >= drop_threshold:
                    alerts.append({
                        "ticker": ticker,
                        "latest_score": latest,
                        "previous_score": previous,
                        "drop": drop,
                        "date": rows[0]["date"]
                    })
    return alerts

