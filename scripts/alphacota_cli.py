import argparse
import sys
import json
import os
from pathlib import Path

# Adicionar o diretório pai (raiz do projeto) ao sys.path para importar os módulos
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.logger import get_logger
from data.universe import get_tickers
from data.fundamentals_scraper import fetch_fundamentals_bulk, get_cache_status
from services.allocation_pipeline import run_allocation_pipeline as run_pipeline

logger = get_logger("CLI")


def update_data(args):
    """Força atualização dos dados de FIIs via scraping."""
    logger.info("Iniciando atualização de dados...")
    tickers = get_tickers()

    if args.ticker:
        tickers = [t.upper() for t in args.ticker]

    if getattr(args, "sample", False):
        tickers = tickers[:5]

    logger.info(f"Buscando dados para {len(tickers)} ativos: {tickers}")
    results = fetch_fundamentals_bulk(tickers, force_refresh=args.force)

    success = sum(1 for r in results.values() if r.get("_source") == "scraper")
    logger.info(f"Atualização concluída! {success}/{len(tickers)} atualizados via scraper.")

    if args.status:
        status = get_cache_status(tickers)
        logger.info(f"Status do cache: {json.dumps(status, indent=2)}")


def pipeline(args):
    """Roda a pipeline completa e exibe os resultados."""
    logger.info(f"Executando pipeline para o perfil: {args.perfil.upper()}")

    capital = args.capital
    if capital < 1000:
        logger.warning(f"Capital de R$ {capital} é muito baixo para alocação diversificada.")

    try:
        resultado = run_pipeline(perfil=args.perfil, target_capital=capital)

        print("\n" + "=" * 50)
        print(f" ALOCAÇÃO OTIMIZADA - PERFIL {args.perfil.upper()}")
        print("=" * 50)

        if "error" in resultado:
            print(f"ERRO: {resultado['error']}")
            sys.exit(1)

        allocs = resultado.get("allocations", {})
        for asset, weight in sorted(allocs.items(), key=lambda x: x[1], reverse=True):
            valor = capital * weight
            print(f"  {asset:6s} | {weight*100:5.1f}% | R$ {valor:10.2f}")

        print("-" * 50)
        print(f"Retorno Esperado:  {resultado.get('expected_return', 0)*100:.2f}% a.a.")
        print(f"Risco (Volatilidade): {resultado.get('volatility', 0)*100:.2f}% a.a.")
        print("=" * 50)

    except Exception as e:
        logger.error(f"Erro ao executar pipeline: {e}", exc_info=True)
        sys.exit(1)


def cache_status(args):
    """Exibe o status do banco de cache."""
    tickers = get_tickers()
    status = get_cache_status(tickers)

    print("\n" + "=" * 50)
    print(" STATUS DO CACHE DE FUNDAMENTOS")
    print("=" * 50)
    print(f"Total de ativos: {status['total']}")
    print(f"Válidos no cache: {status['cached']}")
    print(f"Expirados (stale): {status['stale']}")
    print(f"Inexistentes: {status['missing']}")
    print("=" * 50 + "\n")

    if args.verbose:
        for t, s in status["details"].items():
            if s != "valid" or args.all:
                print(f"  {t:6s}: {s}")
        print()


def main():
    parser = argparse.ArgumentParser(description="AlphaCota CLI - Ferramenta de linha de comando")
    subparsers = parser.add_subparsers(dest="command", help="Comandos disponíveis", required=True)

    # Comando update-data
    parser_update = subparsers.add_parser("update-data", help="Força atualização do banco de dados/cache")
    parser_update.add_argument("--force", action="store_true", help="Ignora o tempo do cache e força recarregamento")
    parser_update.add_argument("--ticker", nargs="+", help="Atualiza apenas os tickers especificados")
    parser_update.add_argument("--status", action="store_true", help="Mostra o status do cache ao finalizar")
    parser_update.add_argument("--sample", action="store_true", help="Testa apenas com 5 ativos")
    parser_update.set_defaults(func=update_data)

    # Comando run-pipeline
    parser_pipeline = subparsers.add_parser("run-pipeline", help="Roda a pipeline no terminal")
    parser_pipeline.add_argument(
        "--perfil",
        type=str,
        choices=["conservador", "moderado", "agressivo"],
        default="moderado",
        help="Perfil do investidor",
    )
    parser_pipeline.add_argument("--capital", type=float, default=100000.0, help="Capital a alocar")
    parser_pipeline.set_defaults(func=pipeline)

    # Comando status
    parser_status = subparsers.add_parser("status", help="Mostra o status do cache atual")
    parser_status.add_argument("-v", "--verbose", action="store_true", help="Mostra os ativos problemáticos")
    parser_status.add_argument("-a", "--all", action="store_true", help="Mostra status de todos os ativos no verbose")
    parser_status.set_defaults(func=cache_status)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
