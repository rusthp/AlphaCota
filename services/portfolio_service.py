from core.decision_engine import generate_decision_report
from infra.database import get_operations, get_proventos, save_portfolio_snapshot
from core.logger import logger


def run_full_cycle(
    user_id: int,
    precos_atuais: dict[str, float],
    alocacao_alvo: dict[str, float],
    aporte_mensal: float,
    taxa_anual_esperada: float,
    renda_alvo_anual: float,
) -> dict:
    """
    Orquestrador master (Service Layer) que conecta o banco de dados
    ao motor de decisão e já salva automaticamente os snapshots.

    Args:
        user_id: ID do Usuário corrente.
        precos_atuais: Dicionário mapeando ticker para preço atual no mercado.
        alocacao_alvo: Dicionário com ticker e o percentual alvo.
        aporte_mensal: Valor total disponível para o novo aporte.
        taxa_anual_esperada: Taxa de retorno anual esperada.
        renda_alvo_anual: Renda passiva anual desejada.

    Returns:
        dict: Relatório consolidado gerado pelo Decision Engine.
    """
    logger.info(f"[User {user_id}] Iniciando ciclo completo de orquestração do portfólio...")

    # 1. Buscar operações via banco
    operacoes = get_operations(user_id)

    # 2. Buscar proventos via banco
    proventos = get_proventos(user_id)

    logger.info(
        f"[User {user_id}] Dados carregados: {len(operacoes)} operações, {len(proventos)} proventos encontrados."
    )

    # 3. Chamar generate_decision_report() com os dados da base
    report = generate_decision_report(
        operacoes=operacoes,
        precos_atuais=precos_atuais,
        proventos=proventos,
        alocacao_alvo=alocacao_alvo,
        aporte_mensal=aporte_mensal,
        taxa_anual_esperada=taxa_anual_esperada,
        renda_alvo_anual=renda_alvo_anual,
    )

    # 4. Salvar o snapshot evolutivo para a memória do sistema isolado no BD
    logger.info(f"[User {user_id}] Gerando snapshot evolutivo...")
    save_portfolio_snapshot(user_id, report)

    logger.info(f"[User {user_id}] Ciclo finalizado com sucesso. Relatório de decisão gerado.")
    # 5. Retornar o contrato fechado (JSON payload)
    return report
