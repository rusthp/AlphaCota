import argparse
import json
import os
import sys

from infra.database import init_db, save_operation, save_provento, get_portfolio_snapshots
from services.portfolio_service import run_full_cycle


def main():
    parser = argparse.ArgumentParser(description="AlphaCota CLI - Sistema de Decisões Financeiras")
    subparsers = parser.add_subparsers(dest="command", help="Comandos disponíveis")

    # 1. init
    subparsers.add_parser("init", help="Inicializa o banco de dados (Cria tabelas no SQLite local)")

    # 2. add-operation
    parser_operation = subparsers.add_parser("add-operation", help="Adiciona uma operação de compra ou venda")
    parser_operation.add_argument("ticker", type=str, help="Código do ativo (ex: BBSE3)")
    parser_operation.add_argument(
        "tipo", type=str, choices=["compra", "venda"], help="O tipo de operação (compra, venda)"
    )
    parser_operation.add_argument("quantidade", type=float, help="Quantidade de cotas movimentadas")
    parser_operation.add_argument("preco", type=float, help="Preço unitário pago ou recebido")

    # 3. add-provento
    parser_provento = subparsers.add_parser("add-provento", help="Adiciona um provento/dividendo recebido")
    parser_provento.add_argument("ticker", type=str, help="Código do ativo que pagou (ex: BBSE3)")
    parser_provento.add_argument("valor", type=float, help="Valor total financeiro recebido")

    # 4. report
    subparsers.add_parser("report", help="Gera o relatório de decisão (Run Full Cycle) e persiste o snapshot histórico")

    # 5. history
    subparsers.add_parser("history", help="Retorna o histórico unificado de snapshots de forma consolidada")

    # 6. backtest
    parser_bt = subparsers.add_parser("backtest", help="Roda backtest histórico e exibe métricas de performance")
    parser_bt.add_argument("--tickers", nargs="+", default=["MXRF11", "HGLG11"], help="Tickers da carteira")
    parser_bt.add_argument("--weights", nargs="+", type=float, default=[0.60, 0.40], help="Pesos (devem somar 1.0)")
    parser_bt.add_argument("--aporte", type=float, default=1000.0, help="Aporte mensal em R$")
    parser_bt.add_argument("--capital", type=float, default=0.0, help="Capital inicial em R$")
    parser_bt.add_argument("--meses", type=int, default=24, help="Número de meses (usa dados sintéticos)")
    parser_bt.add_argument(
        "--rebalance",
        default="quarterly",
        choices=["monthly", "quarterly", "semiannual"],
        help="Frequência de rebalanceamento",
    )

    args = parser.parse_args()

    if args.command == "init":
        init_db()
        print("Banco inicializado com sucesso.")

    elif args.command == "add-operation":
        save_operation(args.ticker, args.tipo, args.quantidade, args.preco)
        print(f"Operação {args.tipo} do ativo {args.ticker} registrada.")

    elif args.command == "add-provento":
        save_provento(args.ticker, args.valor)
        print(f"Provento do ativo {args.ticker} registrado no valor de R$ {args.valor:.2f}.")

    elif args.command == "report":
        # Parâmetros hardcoded temporariamente conforme contrato
        precos_atuais = {"BBSE3": 32.0, "MXRF11": 10.5}
        alocacao_alvo = {"BBSE3": 0.5, "MXRF11": 0.5}
        aporte_mensal = 500.0
        taxa_anual_esperada = 0.10
        renda_alvo_anual = 120000.0

        try:
            report = run_full_cycle(
                precos_atuais=precos_atuais,
                alocacao_alvo=alocacao_alvo,
                aporte_mensal=aporte_mensal,
                taxa_anual_esperada=taxa_anual_esperada,
                renda_alvo_anual=renda_alvo_anual,
            )
            print(json.dumps(report, indent=2))
        except Exception as e:
            print(f"Erro ao orquestrar a geração: {e}")

    elif args.command == "history":
        snapshots = get_portfolio_snapshots()
        if not snapshots:
            print("Nenhum snapshot gerado até o momento.")
        else:
            print(json.dumps(snapshots, indent=2, default=str))

    elif args.command == "backtest":
        from core.backtest_engine import run_backtest, compare_against_benchmark, format_metrics_report
        import random

        tickers = args.tickers
        raw_w = args.weights
        meses = args.meses

        if len(tickers) != len(raw_w):
            print("Erro: número de tickers e pesos deve ser igual.")
            sys.exit(1)

        total_w = sum(raw_w)
        weights = {t: w / total_w for t, w in zip(tickers, raw_w)}

        def _gen(base, n, mu=0.007, sigma=0.03, seed=42):
            random.seed(seed)
            p = [base]
            for _ in range(n - 1):
                p.append(max(0.01, p[-1] * (1 + random.gauss(mu, sigma))))
            return p

        price_series = {t: _gen(10.0 * (i + 1), meses, seed=i) for i, t in enumerate(tickers)}
        dividend_series = {t: [price_series[t][j] * 0.007 for j in range(meses)] for t in tickers}
        benchmark = _gen(120000.0, meses, mu=0.005, sigma=0.05, seed=99)

        result = run_backtest(
            tickers=tickers,
            weights=weights,
            price_series=price_series,
            dividend_series=dividend_series,
            monthly_contribution=args.aporte,
            initial_capital=args.capital,
            rebalance_frequency=args.rebalance,
        )
        comparison = compare_against_benchmark(result, benchmark, args.aporte, args.capital)
        print(format_metrics_report(result, comparison))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
