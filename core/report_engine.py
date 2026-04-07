"""
core/report_engine.py

Geração de relatórios exportáveis para o AlphaCota:
- CSV de carteira (tickers, pesos, métricas)
- HTML tearsheet (patrimônio, backtest metrics, correlação, stress)

Sem dependências externas — usa apenas stdlib.
"""

import csv
import io
import datetime
import math
from typing import Any


def portfolio_to_csv(portfolio: list[dict]) -> str:
    """
    Gera CSV com dados da carteira.

    Args:
        portfolio: Lista de dicts com ticker, quantidade, preco_atual, dividend_mensal.

    Returns:
        str: Conteúdo do CSV em texto.
    """
    output = io.StringIO()
    fieldnames = ["ticker", "quantidade", "preco_atual", "dividend_mensal", "valor_total", "dy_anual_%"]

    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    total_valor = sum(p["quantidade"] * p.get("preco_atual", 0) for p in portfolio)

    for p in portfolio:
        qty = p.get("quantidade", 0)
        price = p.get("preco_atual", 0.0)
        div = p.get("dividend_mensal", 0.0)
        valor = qty * price
        dy = (div * 12 / price * 100) if price > 0 else 0.0

        writer.writerow(
            {
                "ticker": p.get("ticker", "?"),
                "quantidade": qty,
                "preco_atual": f"{price:.2f}",
                "dividend_mensal": f"{div:.4f}",
                "valor_total": f"{valor:.2f}",
                "dy_anual_%": f"{dy:.2f}",
            }
        )

    return output.getvalue()


def backtest_metrics_to_csv(metrics: dict) -> str:
    """
    Gera CSV das métricas de backtest.

    Args:
        metrics: Dict retornado por run_backtest (chaves: cagr, sharpe, sortino, etc.)

    Returns:
        str: Conteúdo CSV.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Métrica", "Valor"])
    for key, val in metrics.items():
        if isinstance(val, float):
            writer.writerow([key, f"{val:.4f}"])
        else:
            writer.writerow([key, val])
    return output.getvalue()


def generate_html_tearsheet(
    portfolio: list[dict],
    backtest_metrics: dict | None = None,
    correlation_matrix: dict | None = None,
    stress_summary: dict | None = None,
    title: str = "AlphaCota — Portfolio Report",
) -> str:
    """
    Gera um relatório HTML estático completo com estilo escuro.

    Args:
        portfolio: Lista de ativos da carteira.
        backtest_metrics: Dict de métricas de backtest (opcional).
        correlation_matrix: Matriz de correlação (opcional).
        stress_summary: Sumário de stress testing (opcional).
        title: Título do relatório.

    Returns:
        str: HTML completo pronto para download.
    """
    now = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    total_valor = sum(p.get("quantidade", 0) * p.get("preco_atual", 0) for p in portfolio)
    total_dy = sum(p.get("dividend_mensal", 0) for p in portfolio)

    # --- Carteira ---
    portfolio_rows = ""
    for p in portfolio:
        qty = p.get("quantidade", 0)
        price = p.get("preco_atual", 0.0)
        div = p.get("dividend_mensal", 0.0)
        valor = qty * price
        dy = (div * 12 / price * 100) if price > 0 else 0.0
        pct = (valor / total_valor * 100) if total_valor > 0 else 0.0
        portfolio_rows += f"""
        <tr>
          <td><b>{p.get('ticker','?')}</b></td>
          <td>{qty}</td>
          <td>R$ {price:.2f}</td>
          <td>R$ {div:.4f}</td>
          <td>R$ {valor:,.2f}</td>
          <td>{pct:.1f}%</td>
          <td>{dy:.2f}%</td>
        </tr>"""

    # --- Backtest ---
    backtest_html = ""
    if backtest_metrics:
        bk_rows = ""
        labels = {
            "cagr": "CAGR",
            "sharpe": "Sharpe Ratio",
            "sortino": "Sortino",
            "max_drawdown": "Max Drawdown",
            "annual_volatility": "Volatilidade Anual",
            "total_return": "Retorno Total",
        }
        for k, label in labels.items():
            val = backtest_metrics.get(k)
            if val is not None:
                if isinstance(val, float):
                    bk_rows += f"<tr><td>{label}</td><td><b>{val*100:.2f}%</b></td></tr>"
                else:
                    bk_rows += f"<tr><td>{label}</td><td><b>{val}</b></td></tr>"

        backtest_html = f"""
        <h2>📊 Backtest — Performance Histórica</h2>
        <table><thead><tr><th>Métrica</th><th>Valor</th></tr></thead>
        <tbody>{bk_rows}</tbody></table>"""

    # --- Correlação ---
    corr_html = ""
    if correlation_matrix:
        tickers = list(correlation_matrix.keys())
        header = "<tr><th></th>" + "".join(f"<th>{t}</th>" for t in tickers) + "</tr>"
        rows = ""
        for r in tickers:
            row_vals = correlation_matrix.get(r, {})
            cells = ""
            for c in tickers:
                v = row_vals.get(c, 0.0)
                color = "#2e7d32" if abs(v) < 0.5 else "#f57c00" if abs(v) < 0.75 else "#c62828"
                cells += f"<td style='background:{color};color:#fff;'>{v:.2f}</td>"
            rows += f"<tr><td><b>{r}</b></td>{cells}</tr>"

        corr_html = f"""
        <h2>🔗 Matriz de Correlação</h2>
        <table><thead>{header}</thead><tbody>{rows}</tbody></table>"""

    # --- Stress ---
    stress_html = ""
    if stress_summary:
        stress_html = f"""
        <h2>⚡ Stress Testing — Resumo</h2>
        <table>
          <tr><th>Pior Cenário</th><td>{stress_summary.get('worst_scenario','—')}</td></tr>
          <tr><th>Drawdown Máximo</th><td>{stress_summary.get('worst_drawdown',0)*100:+.1f}%</td></tr>
          <tr><th>Drawdown Médio</th><td>{stress_summary.get('avg_drawdown',0)*100:+.1f}%</td></tr>
          <tr><th>Corte Médio de DY</th><td>{stress_summary.get('avg_div_cut',0)*100:+.1f}%</td></tr>
          <tr><th>Cenários Testados</th><td>{stress_summary.get('n_scenarios','—')}</td></tr>
        </table>"""

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <title>{title}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Segoe UI', sans-serif; background: #0e1117; color: #fafafa; padding: 2rem; }}
    h1 {{ color: #4fc3f7; border-bottom: 2px solid #4fc3f7; padding-bottom: .5rem; margin-bottom: 1.5rem; }}
    h2 {{ color: #81d4fa; margin: 2rem 0 1rem 0; }}
    .header-meta {{ color: #aaa; font-size: .85rem; margin-bottom: 2rem; }}
    .kpi {{ display: flex; gap: 1.5rem; margin-bottom: 2rem; flex-wrap: wrap; }}
    .kpi-card {{ background: #1e2130; border-radius: 8px; padding: 1rem 1.5rem; min-width: 160px; }}
    .kpi-card .label {{ font-size: .75rem; color: #aaa; text-transform: uppercase; letter-spacing: .05em; }}
    .kpi-card .value {{ font-size: 1.5rem; font-weight: 700; color: #4fc3f7; margin-top: .25rem; }}
    table {{ width: 100%; border-collapse: collapse; margin-bottom: 1.5rem; }}
    th {{ background: #1a237e; color: #e3f2fd; padding: .6rem .8rem; text-align: left; font-size: .8rem; }}
    td {{ padding: .5rem .8rem; border-bottom: 1px solid #1e2130; font-size: .85rem; }}
    tr:hover td {{ background: #1e2130; }}
    footer {{ margin-top: 3rem; color: #555; font-size: .75rem; text-align: center; }}
  </style>
</head>
<body>
  <h1>🏦 {title}</h1>
  <p class="header-meta">Gerado em {now} · AlphaCota v2</p>

  <div class="kpi">
    <div class="kpi-card">
      <div class="label">Patrimônio Total</div>
      <div class="value">R$ {total_valor:,.0f}</div>
    </div>
    <div class="kpi-card">
      <div class="label">DY Mensal Total</div>
      <div class="value">R$ {total_dy:.2f}</div>
    </div>
    <div class="kpi-card">
      <div class="label">DY Anual Est.</div>
      <div class="value">{(total_dy*12/total_valor*100) if total_valor > 0 else 0:.2f}%</div>
    </div>
    <div class="kpi-card">
      <div class="label">Ativos</div>
      <div class="value">{len(portfolio)}</div>
    </div>
  </div>

  <h2>💼 Carteira Atual</h2>
  <table>
    <thead>
      <tr><th>Ticker</th><th>Qtd</th><th>Preço</th><th>DY/mês</th><th>Valor</th><th>% Cart.</th><th>DY Anual</th></tr>
    </thead>
    <tbody>{portfolio_rows}</tbody>
  </table>

  {backtest_html}
  {corr_html}
  {stress_html}

  <footer>AlphaCota v2 · Motor Quantitativo · {now}</footer>
</body>
</html>"""

    return html


def generate_portfolio_csv_download(portfolio: list[dict]) -> bytes:
    """Retorna bytes UTF-8 do CSV de carteira para st.download_button."""
    return portfolio_to_csv(portfolio).encode("utf-8")


def generate_html_download(html: str) -> bytes:
    """Retorna bytes UTF-8 do HTML tearsheet para st.download_button."""
    return html.encode("utf-8")
