from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
import os

from services.portfolio_service import run_full_cycle
from infra.database import (
    get_portfolio_snapshots,
    create_user,
    get_user_by_email
)
from core.security import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user
)

app = FastAPI(title="AlphaCota API")

class UserCreate(BaseModel):
    email: str
    password: str

class ReportRequest(BaseModel):
    precos_atuais: dict[str, float]
    alocacao_alvo: dict[str, float]
    aporte_mensal: float
    taxa_anual_esperada: float
    renda_alvo_anual: float

@app.get("/health")
def health_check():
    """Teste de vida."""
    return {"status": "ok"}

@app.post("/register")
def register(user: UserCreate):
    hashed_pwd = hash_password(user.password)
    user_id = create_user(user.email, hashed_pwd)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nome de usuário (e-mail) já registrado"
        )
    return {"message": "Usuário registrado com sucesso", "user_id": user_id}

@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = get_user_by_email(form_data.username)
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais incorretas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token({"user_id": user["id"]})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/report")
def generate_report(request: ReportRequest, user_id: int = Depends(get_current_user)):
    """
    Recebe as premissas atuais e alvos, delega para o Service Layer 
    para gerar o relatório de decisão atual e persistir histórico.
    """
    report = run_full_cycle(
        user_id=user_id,
        precos_atuais=request.precos_atuais,
        alocacao_alvo=request.alocacao_alvo,
        aporte_mensal=request.aporte_mensal,
        taxa_anual_esperada=request.taxa_anual_esperada,
        renda_alvo_anual=request.renda_alvo_anual
    )
    return report

@app.get("/history")
def get_history(user_id: int = Depends(get_current_user)):
    """Recupera o histórico da carteira evolutiva no tempo."""
    snapshots = get_portfolio_snapshots(user_id=user_id)
    return snapshots
