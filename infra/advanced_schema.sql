-- Estrutura de banco usando UUIDs e Constraints Escaláveis

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY, -- Simulação de UUID
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_profile (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    aporte_mensal REAL NOT NULL,
    objetivo TEXT CHECK(objetivo IN ('crescimento', 'dividendos')) NOT NULL,
    perfil_risco TEXT CHECK(perfil_risco IN ('conservador', 'moderado', 'agressivo')) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_user_profile_user_id ON user_profile(user_id);

CREATE TABLE IF NOT EXISTS assets (
    id TEXT PRIMARY KEY,
    ticker TEXT UNIQUE NOT NULL,
    classe TEXT CHECK(classe IN ('ETF', 'ACAO', 'FII')) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS portfolio (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    quantidade REAL NOT NULL,
    preco_medio REAL NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(asset_id) REFERENCES assets(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_portfolio_user_id ON portfolio(user_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_asset_id ON portfolio(asset_id);

CREATE TABLE IF NOT EXISTS asset_universe (
    id TEXT PRIMARY KEY,
    ticker TEXT UNIQUE NOT NULL,
    classe TEXT CHECK(classe IN ('ETF', 'ACAO', 'FII')) NOT NULL,
    nome TEXT NOT NULL,
    ativo BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_asset_universe_classe ON asset_universe(classe);
