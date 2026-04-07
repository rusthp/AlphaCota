# core/state_repository.py
import sqlite3
import json


def init_db(connection: sqlite3.Connection) -> None:
    """
    Inicializa o banco de dados criando as tabelas se nao existirem.
    """
    cursor = connection.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS portfolio_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        investor_profile TEXT NOT NULL,
        expected_return REAL,
        monte_carlo_median REAL
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS asset_allocations (
        snapshot_id INTEGER,
        ticker TEXT,
        asset_class TEXT,
        weight REAL,
        score REAL,
        FOREIGN KEY(snapshot_id) REFERENCES portfolio_snapshots(id)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS score_history (
        timestamp TEXT,
        ticker TEXT,
        fundamental_score REAL,
        momentum_score REAL,
        final_score REAL,
        altman_z REAL
    );
    """)

    connection.commit()


def save_snapshot(connection: sqlite3.Connection, snapshot_data: dict) -> int:
    """
    Salva uma 'fotografia' (snapshot) geral do portfolio e retorna o ID gerado.
    """
    cursor = connection.cursor()
    cursor.execute(
        """
        INSERT INTO portfolio_snapshots (timestamp, investor_profile, expected_return, monte_carlo_median)
        VALUES (?, ?, ?, ?)
    """,
        (
            snapshot_data["timestamp"],
            snapshot_data["investor_profile"],
            snapshot_data.get("expected_return", 0.0),  # CAGR
            snapshot_data.get("monte_carlo_median", 0.0),
        ),
    )
    connection.commit()
    return cursor.lastrowid


def save_allocations(connection: sqlite3.Connection, snapshot_id: int, allocations: list[dict]) -> None:
    """
    Salva os pesos e ativos escolhidos vinculados ao ID do snapshot.
    """
    cursor = connection.cursor()
    data = []
    for alloc in allocations:
        data.append(
            (
                snapshot_id,
                alloc["ticker"],
                alloc.get("asset_class", "UNKNOWN"),
                alloc["weight"],
                alloc.get("score", 0.0),
            )
        )

    cursor.executemany(
        """
        INSERT INTO asset_allocations (snapshot_id, ticker, asset_class, weight, score)
        VALUES (?, ?, ?, ?, ?)
    """,
        data,
    )
    connection.commit()


def save_scores(connection: sqlite3.Connection, scores: list[dict]) -> None:
    """
    Salva o log cru dos scores individuais gerados pelo engine Quantamental.
    """
    cursor = connection.cursor()
    data = []
    for s in scores:
        data.append(
            (
                s["timestamp"],
                s["ticker"],
                s.get("fundamental_score", 0.0),
                s.get("momentum_score", 0.0),
                s.get("final_score", 0.0),
                s.get("altman_z", 0.0),
            )
        )

    cursor.executemany(
        """
        INSERT INTO score_history (timestamp, ticker, fundamental_score, momentum_score, final_score, altman_z)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        data,
    )
    connection.commit()


def get_last_snapshot(connection: sqlite3.Connection) -> dict | None:
    """
    Recupera o ultimo snapshot registrado, incluindo as alocacoes.
    """
    cursor = connection.cursor()
    cursor.row_factory = sqlite3.Row

    # 1. Pega o ultimo portfolio
    cursor.execute("SELECT * FROM portfolio_snapshots ORDER BY timestamp DESC, id DESC LIMIT 1")
    row = cursor.fetchone()

    if not row:
        return None

    snapshot = dict(row)
    snapshot_id = snapshot["id"]

    # 2. Pega as alocacoes vinculadas
    cursor.execute("SELECT * FROM asset_allocations WHERE snapshot_id = ?", (snapshot_id,))
    allocs = [dict(r) for r in cursor.fetchall()]

    snapshot["allocations"] = allocs
    return snapshot
