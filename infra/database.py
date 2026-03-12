import sqlite3
from typing import Optional
from core.config import settings

def _get_connection() -> sqlite3.Connection:
    """Abre e retorna a conexão com o banco SQLite."""
    conn = sqlite3.connect(settings.database_path)
    # Permite acessar as colunas pelo nome (dict-like)
    conn.row_factory = sqlite3.Row
    # Ativa integridade referencial do SQLite
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db() -> None:
    """Cria as tabelas operações, proventos, snapshots e usuários se não existirem."""
    conn = _get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS operations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            tipo TEXT NOT NULL,
            quantidade REAL NOT NULL,
            preco REAL NOT NULL,
            data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS proventos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            valor REAL NOT NULL,
            data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            valor_total REAL NOT NULL,
            lucro_prejuizo_total REAL NOT NULL,
            lucro_prejuizo_percentual_total REAL NOT NULL,
            renda_total REAL NOT NULL,
            yield_percentual REAL NOT NULL,
            patrimonio_necessario REAL NOT NULL,
            anos_estimados REAL NOT NULL,
            data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)
    
    conn.commit()
    conn.close()

def save_operation(user_id: int, ticker: str, tipo: str, quantidade: float, preco: float) -> None:
    """
    Salva uma nova operação (compra ou venda) no banco de dados para determinado usuário.
    """
    conn = _get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO operations (user_id, ticker, tipo, quantidade, preco)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, ticker, tipo, quantidade, preco))
    
    conn.commit()
    conn.close()

def save_provento(user_id: int, ticker: str, valor: float) -> None:
    """
    Salva o recebimento de proventos no banco de dados para determinado usuário.
    """
    conn = _get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO proventos (user_id, ticker, valor)
        VALUES (?, ?, ?)
    """, (user_id, ticker, valor))
    
    conn.commit()
    conn.close()

def save_portfolio_snapshot(user_id: int, report: dict) -> None:
    """
    Extrai as métricas de um JSON (gerado pelo decision_engine)
    e persiste um snapshot da evolução da carteira de forma isolada para o usuário.
    """
    resumo = report.get("resumo_carteira", {})
    renda = report.get("renda_passiva", {})
    fogo = report.get("fogo_financeiro", {})
    
    valor_total = resumo.get("valor_total", 0.0)
    lucro_prejuizo_total = resumo.get("lucro_prejuizo_total", 0.0)
    lp_pct_total = resumo.get("lucro_prejuizo_percentual_total", 0.0)
    
    renda_total = renda.get("renda_total", 0.0)
    yield_pct = renda.get("yield_percentual", 0.0)
    
    patr_necessario = fogo.get("patrimonio_necessario", 0.0)
    anos_est = fogo.get("anos_estimados", 0.0)
    
    conn = _get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO portfolio_snapshots (
            user_id,
            valor_total,
            lucro_prejuizo_total,
            lucro_prejuizo_percentual_total,
            renda_total,
            yield_percentual,
            patrimonio_necessario,
            anos_estimados
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        valor_total,
        lucro_prejuizo_total,
        lp_pct_total,
        renda_total,
        yield_pct,
        patr_necessario,
        anos_est
    ))
    
    conn.commit()
    conn.close()

def get_operations(user_id: int) -> list[dict[str, float | str | int]]:
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, ticker, tipo, quantidade, preco, data_criacao FROM operations WHERE user_id = ? ORDER BY id ASC", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_proventos(user_id: int) -> list[dict[str, float | str | int]]:
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, ticker, valor, data_criacao FROM proventos WHERE user_id = ? ORDER BY id ASC", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_portfolio_snapshots(user_id: int) -> list[dict[str, float | str | int]]:
    """
    Recupera todo o histórico evolutivo de snapshots, ordenado por data ascendente para o usuário.
    """
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, valor_total, lucro_prejuizo_total, lucro_prejuizo_percentual_total, renda_total, yield_percentual, patrimonio_necessario, anos_estimados, data_criacao FROM portfolio_snapshots WHERE user_id = ? ORDER BY data_criacao ASC", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def create_user(email: str, hashed_password: str) -> Optional[int]:
    """Cria um novo usuário e retorna o seu ID inserido."""
    conn = _get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (email, hashed_password) VALUES (?, ?)", (email, hashed_password))
        conn.commit()
        user_id = cursor.lastrowid
        return user_id
    except sqlite3.IntegrityError:
        # E-mail já existe
        return None
    finally:
        conn.close()

def get_user_by_email(email: str) -> Optional[dict]:
    """Recupera um usuário pelo e-mail se ele existir."""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, hashed_password FROM users WHERE email = ?", (email,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None
