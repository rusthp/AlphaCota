import os
import sys
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import seaborn as sns

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.simulador_service import simulate_monte_carlo
from core.profile_allocator import getTargetAllocation
from core.backtest_engine import run_backtest, compare_against_benchmark, format_metrics_report
from core.correlation_engine import (
    build_correlation_matrix,
    analyse_portfolio_risk,
    suggest_rebalance_with_correlation,
)
from core.markowitz_engine import (
    compare_strategies,
    format_strategy_report,
)

st.set_page_config(
    page_title="AlphaCota — Intelligence Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Sidebar global
# ---------------------------------------------------------------------------
st.sidebar.image("https://img.icons8.com/fluency/48/financial-growth-analysis.png", width=48)
st.sidebar.title("AlphaCota")
st.sidebar.markdown("*Motor Quantitativo para FIIs*")
st.sidebar.markdown("---")

perfil_selecionado = st.sidebar.selectbox(
    "Perfil de Investidor",
    ["conservador", "moderado", "agressivo"],
    index=1,
)
aporte_mensal = st.sidebar.number_input("Aporte Mensal (R$)", value=1000.0, step=100.0, min_value=0.0)
st.sidebar.markdown("---")
st.sidebar.caption("AlphaCota v2 · Fases 1-2.2 ✅")

# ---------------------------------------------------------------------------
# Abas principais
# ---------------------------------------------------------------------------
tab_projecao, tab_backtest, tab_risco, tab_markowitz = st.tabs([
    "📈 Projeção Futura (Monte Carlo)",
    "🔬 Evidência Histórica (Backtest)",
    "🛡️ Risco & Correlação",
    "🔷 Markowitz — Fronteira Eficiente",
])


# ===========================================================================
# ABA 1 — MONTE CARLO (original melhorada)
# ===========================================================================
with tab_projecao:
    st.header("Projeção do Seu Patrimônio")
    st.markdown("Simula centenas de futuros possíveis com base no seu perfil e aporte mensal.")

    col_param1, col_param2 = st.columns([2, 1])
    with col_param1:
        meses_simulacao = st.slider("Horizonte de Investimento (meses)", 12, 240, 60, step=12,
                                     format="%d meses")
    with col_param2:
        with st.expander("⚙️ Avançado"):
            simulacoes = st.number_input("Caminhos Simulados", value=500, step=100, min_value=100)

    target_allocation = getTargetAllocation(perfil_selecionado)

    portfolio_inicial = [
        {'ticker': 'IVVB11', 'classe': 'ETF',  'quantidade': 10,  'preco_atual': 250.0},
        {'ticker': 'BBSE3',  'classe': 'ACAO',  'quantidade': 50,  'preco_atual': 30.0},
        {'ticker': 'MXRF11', 'classe': 'FII',   'quantidade': 100, 'preco_atual': 10.0},
    ]
    asset_universe = [
        {'ticker': 'IVVB11', 'classe': 'ETF',  'ativo': True, 'preco_atual': 250.0},
        {'ticker': 'BNDX11', 'classe': 'ETF',  'ativo': True, 'preco_atual': 100.0},
        {'ticker': 'BBSE3',  'classe': 'ACAO', 'ativo': True, 'preco_atual': 30.0},
        {'ticker': 'WEGE3',  'classe': 'ACAO', 'ativo': True, 'preco_atual': 40.0},
        {'ticker': 'MXRF11', 'classe': 'FII',  'ativo': True, 'preco_atual': 10.0},
        {'ticker': 'HGLG11', 'classe': 'FII',  'ativo': True, 'preco_atual': 160.0},
    ]
    growth_rates  = {"ETF": 0.08, "ACAO": 0.12, "FII": 0.06}
    volatilities  = {"ETF": 0.15, "ACAO": 0.30, "FII": 0.10}

    if st.button("🚀 Projetar Meu Futuro", type="primary", key="btn_monte"):
        with st.spinner("Simulando centenas de futuros possíveis..."):
            resultado = simulate_monte_carlo(
                portfolio_inicial=portfolio_inicial,
                asset_universe=asset_universe,
                target_allocation=target_allocation,
                aporte_mensal=aporte_mensal,
                growth_rates=growth_rates,
                volatilities=volatilities,
                meses=int(meses_simulacao),
                simulacoes=int(simulacoes),
            )

        mediana_vf   = resultado["mediana_valor_final"]
        p10          = resultado["percentil_10"]
        p90          = resultado["percentil_90"]
        prob_prejuizo = resultado["probabilidade_prejuizo"]
        dd_medio     = resultado["drawdown_medio"]
        cagr_medio   = resultado["retorno_anualizado_medio"]

        valor_inicial   = sum(a["quantidade"] * a.get("preco_atual", 0) for a in portfolio_inicial)
        total_investido = valor_inicial + (aporte_mensal * meses_simulacao)
        prob_lucro      = 1.0 - prob_prejuizo

        st.success("Projeção concluída!")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🎯 Patrimônio Mediano", f"R$ {mediana_vf:,.0f}",
                  delta=f"+{((mediana_vf/total_investido)-1)*100:.0f}% sobre aportes")
        c2.metric("📈 CAGR Médio", f"{cagr_medio*100:.1f}% a.a.")
        c3.metric("📉 Drawdown Médio", f"-{dd_medio*100:.1f}%")
        c4.metric("✅ Prob. de Lucro", f"{prob_lucro*100:.1f}%")

        st.markdown("---")
        st.subheader("Faixa de Cenários")
        scol1, scol2, scol3 = st.columns(3)
        with scol1:
            st.info(f"**🟢 Otimista**\n\n# R$ {p90:,.0f}")
        with scol2:
            st.success(f"**🟡 Provável**\n\n# R$ {mediana_vf:,.0f}")
        with scol3:
            st.warning(f"**🔴 Estressado**\n\n# R$ {p10:,.0f}")

        st.markdown("---")
        col_g1, col_g2 = st.columns(2)
        valores_finais = resultado["valores_finais_lista"]
        volatilidades_lista = resultado["volatilidades_lista"]
        cagrs_lista = resultado["cagrs_lista"]

        with col_g1:
            st.markdown("**Distribuição do Resultado Final**")
            fig, ax = plt.subplots(figsize=(8, 4))
            sns.histplot(valores_finais, bins=40, kde=True, color="#4CAF50", ax=ax)
            ax.axvline(total_investido, color="#f44336", linestyle="--", label="Total investido")
            ax.axvline(mediana_vf, color="#2196F3", linestyle="-", label="Mediana")
            ax.set_xlabel("Patrimônio (R$)")
            ax.set_ylabel("Frequência")
            ax.legend()
            st.pyplot(fig)

        with col_g2:
            st.markdown("**Risco × Retorno (cada ponto = 1 simulação)**")
            df_scatter = pd.DataFrame({
                "Volatilidade a.a. (%)": [v * 100 for v in volatilidades_lista],
                "CAGR (%)": [c * 100 for c in cagrs_lista],
            })
            fig2, ax2 = plt.subplots(figsize=(8, 4))
            sns.scatterplot(data=df_scatter, x="Volatilidade a.a. (%)", y="CAGR (%)",
                            alpha=0.3, color="#9C27B0", ax=ax2)
            ax2.axhline(0, color="red", linewidth=0.8, linestyle="--")
            st.pyplot(fig2)

        st.info(
            f"Em média, espere quedas temporárias de **{dd_medio*100:.1f}%**. "
            f"O motor AlphaCota rebalanceia automaticamente para que você sempre "
            f"compre mais do que está barato. Mantenha os aportes de **R$ {aporte_mensal:,.0f}/mês**."
        )
    else:
        st.info("Configure seu perfil na barra lateral e clique em **Projetar Meu Futuro**.")


# ===========================================================================
# ABA 2 — BACKTEST HISTÓRICO
# ===========================================================================
with tab_backtest:
    st.header("Evidência Histórica — Backtest")
    st.markdown(
        "Teste quanto uma estratégia de aportes mensais teria rendido **com dados reais históricos**, "
        "comparando contra o IBOVESPA. **Sem dados reais, use o modo de demonstração (dados sintéticos).**"
    )

    st.info(
        "💡 **Para usar dados reais:** rode `python scripts/bootstrap_data.py` uma vez para "
        "baixar o histórico de preços dos FIIs via yfinance. Os dados ficam em `data/historical_prices/`."
    )

    st.markdown("---")

    # --- Configuração do backtest ---
    bcol1, bcol2, bcol3 = st.columns(3)
    with bcol1:
        bt_capital = st.number_input("Capital Inicial (R$)", value=5000.0, step=500.0, min_value=0.0)
    with bcol2:
        bt_meses = st.slider("Período (meses)", 12, 60, 24, step=6)
    with bcol3:
        bt_rebalance = st.selectbox(
            "Frequência de Rebalanceamento",
            ["monthly", "quarterly", "semiannual"],
            index=1,
            format_func=lambda x: {"monthly": "Mensal", "quarterly": "Trimestral", "semiannual": "Semestral"}[x],
        )

    st.markdown("**Carteira para backtest** (modo demonstração — dados sintéticos crescentes)")
    tickers_demo = ["MXRF11", "HGLG11", "KNCR11"]
    weights_demo = {"MXRF11": 0.40, "HGLG11": 0.35, "KNCR11": 0.25}

    demo_info_cols = st.columns(len(tickers_demo))
    for i, t in enumerate(tickers_demo):
        demo_info_cols[i].metric(t, f"{weights_demo[t]*100:.0f}%")

    if st.button("🔬 Rodar Backtest", type="primary", key="btn_backtest"):
        with st.spinner("Calculando backtest histórico..."):

            # ---------------------------------------------------------------
            # Dados sintéticos realistas para demonstração
            # (serão substituídos por dados reais quando bootstrap rodar)
            # ---------------------------------------------------------------
            import math as _math

            def _gen_prices(base: float, n: int, mu: float, sigma: float, seed: int) -> list[float]:
                """Série de preços com retorno esperado mu e volatilidade sigma."""
                import random
                random.seed(seed)
                prices = [base]
                for _ in range(n - 1):
                    r = random.gauss(mu, sigma)
                    prices.append(max(0.01, prices[-1] * (1 + r)))
                return prices

            price_series = {
                "MXRF11": _gen_prices(9.80,  bt_meses, 0.007, 0.03, seed=42),
                "HGLG11": _gen_prices(155.0, bt_meses, 0.008, 0.04, seed=43),
                "KNCR11": _gen_prices(97.0,  bt_meses, 0.006, 0.025, seed=44),
            }
            dividend_series = {
                "MXRF11": [0.085 * price_series["MXRF11"][i] / 12 for i in range(bt_meses)],
                "HGLG11": [0.075 * price_series["HGLG11"][i] / 12 for i in range(bt_meses)],
                "KNCR11": [0.090 * price_series["KNCR11"][i] / 12 for i in range(bt_meses)],
            }
            benchmark_prices = _gen_prices(120000.0, bt_meses, 0.006, 0.05, seed=99)

            # ---------------------------------------------------------------
            # Rodar backtest
            # ---------------------------------------------------------------
            try:
                result = run_backtest(
                    tickers=tickers_demo,
                    weights=weights_demo,
                    price_series=price_series,
                    dividend_series=dividend_series,
                    monthly_contribution=aporte_mensal,
                    initial_capital=bt_capital,
                    rebalance_frequency=bt_rebalance,
                )
                result.start_date = "demo"
                result.end_date   = "demo"

                comparison = compare_against_benchmark(
                    result, benchmark_prices, aporte_mensal, bt_capital
                )

            except Exception as e:
                st.error(f"Erro ao rodar backtest: {e}")
                st.stop()

        st.success("Backtest concluído!")

        # --- Métricas principais ---
        m = result.metrics
        bm = comparison.get("benchmark_ifix", {})
        alpha = comparison.get("alpha", 0.0)

        mc1, mc2, mc3, mc4, mc5 = st.columns(5)
        mc1.metric("💰 Valor Final",    f"R$ {result.final_value:,.0f}",
                   delta=f"Investido: R$ {result.total_invested:,.0f}")
        mc2.metric("📈 CAGR",           f"{m.cagr*100:.2f}% a.a.",
                   delta=f"IFIX: {bm.get('cagr',0)*100:.2f}%")
        mc3.metric("⚡ Sharpe",         f"{m.sharpe_ratio:.2f}")
        mc4.metric("📉 Max Drawdown",   f"{m.max_drawdown*100:.2f}%")
        mc5.metric("🎯 Alpha vs IFIX",  f"{alpha*100:+.2f}% a.a.",
                   delta="✅ Bateu" if comparison.get("bateu_benchmark") else "❌ Perdeu",
                   delta_color="normal" if comparison.get("bateu_benchmark") else "inverse")

        st.markdown("---")

        # --- Gráfico de evolução patrimonial ---
        snapshots = result.monthly_snapshots
        meses_labels = [f"M{s['month']}" for s in snapshots]
        valores = [s["portfolio_value"] for s in snapshots]

        # Simular benchmark na mesma escala
        bm_holdings = (bt_capital / benchmark_prices[0]) if benchmark_prices[0] > 0 else 0
        bm_values = []
        for i, bm_price in enumerate(benchmark_prices[:bt_meses]):
            if bm_price > 0:
                bm_holdings += aporte_mensal / bm_price
            bm_values.append(bm_holdings * bm_price)

        fig3, ax3 = plt.subplots(figsize=(12, 5))
        ax3.plot(meses_labels, valores, color="#4CAF50", linewidth=2.5, label="Carteira AlphaCota")
        ax3.plot(meses_labels, bm_values[:len(meses_labels)],
                 color="#FF9800", linewidth=1.8, linestyle="--", label="Benchmark (IBOV)")

        # Marcar meses de rebalanceamento
        rebalance_months = [s["month"] - 1 for s in snapshots if s.get("rebalanced")]
        ax3.scatter(
            [meses_labels[i] for i in rebalance_months],
            [valores[i] for i in rebalance_months],
            color="#2196F3", zorder=5, s=50, label="Rebalanceamento"
        )

        ax3.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"R$ {x:,.0f}"))
        ax3.set_xlabel("Mês")
        ax3.set_ylabel("Patrimônio (R$)")
        ax3.set_title("Evolução Patrimonial — Carteira vs Benchmark")
        ax3.legend()
        ax3.grid(axis="y", alpha=0.3)
        plt.xticks(rotation=45, fontsize=7)
        plt.tight_layout()
        st.pyplot(fig3)

        st.markdown("---")

        # --- Tabela de métricas comparativas ---
        st.subheader("Métricas Comparativas")
        df_compare = pd.DataFrame({
            "Métrica": ["CAGR (a.a.)", "Sharpe Ratio", "Sortino Ratio", "Max Drawdown", "Volatilidade a.a.", "Valor Final"],
            "Carteira AlphaCota": [
                f"{m.cagr*100:.2f}%",
                f"{m.sharpe_ratio:.3f}",
                f"{m.sortino_ratio:.3f}",
                f"{m.max_drawdown*100:.2f}%",
                f"{m.annual_volatility*100:.2f}%",
                f"R$ {result.final_value:,.2f}",
            ],
            "Benchmark (IBOV)": [
                f"{bm.get('cagr', 0)*100:.2f}%",
                f"{bm.get('sharpe_ratio', 0):.3f}",
                f"{bm.get('sortino_ratio', 0):.3f}",
                f"{bm.get('max_drawdown', 0)*100:.2f}%",
                f"{bm.get('annual_volatility', 0)*100:.2f}%",
                f"R$ {bm.get('valor_final', 0):,.2f}",
            ],
        })
        st.dataframe(df_compare, use_container_width=True, hide_index=True)

        # --- Relatório textual completo ---
        with st.expander("📋 Relatório Completo (texto)"):
            st.code(format_metrics_report(result, comparison), language="")

        # --- Evolução dos dividendos recebidos ---
        st.markdown("---")
        st.subheader("💰 Dividendos Reinvestidos por Mês")
        div_values = [s.get("dividend_cash", 0) for s in snapshots]
        fig4, ax4 = plt.subplots(figsize=(12, 3))
        ax4.bar(meses_labels, div_values, color="#8BC34A", alpha=0.8)
        ax4.set_xlabel("Mês")
        ax4.set_ylabel("R$")
        ax4.grid(axis="y", alpha=0.3)
        plt.xticks(rotation=45, fontsize=7)
        plt.tight_layout()
        st.pyplot(fig4)

    else:
        st.markdown("""
        ### Como funciona o Backtest

        | Conceito | Explicação |
        |---|---|
        | **Aportes Mensais** | Simulação de compra mensal com o valor configurado |
        | **Rebalanceamento** | Reajusta os pesos da carteira periodicamente |
        | **Dividendos** | Proventos reinvestidos automaticamente |
        | **CAGR** | Crescimento anual composto real da estratégia |
        | **Sharpe Ratio** | Retorno por unidade de risco. >1 é bom, >2 é excelente |
        | **Max Drawdown** | A maior queda consecutiva que você teria sofrido |
        | **Alpha** | Diferença de retorno anual em relação ao benchmark |

        Configure acima e clique em **Rodar Backtest**.
        """)


# ===========================================================================
# ABA 3 — RISCO & CORRELAÇÃO
# ===========================================================================
with tab_risco:
    st.header("🛡️ Risco & Correlação da Carteira")
    st.markdown(
        "Analise a correlação entre os FIIs da sua carteira, a concentração setorial "
        "e o risco sistêmico. **Alta correlação = diversificação falsa.**"
    )

    # Mapeamento setorial padrão
    SECTOR_MAP_DEFAULT = {
        "MXRF11": "Papel (CRI)",
        "KNCR11": "Papel (CRI)",
        "RECR11": "Papel (CRI)",
        "MCCI11": "Papel (CRI)",
        "HGLG11": "Logística",
        "XPLG11": "Logística",
        "BTLG11": "Logística",
        "XPML11": "Shopping",
        "MALL11": "Shopping",
        "VISC11": "Shopping",
        "BRCR11": "Lajes Corp.",
        "JSRE11": "Lajes Corp.",
        "BCFF11": "Fundo de Fundos",
        "HFOF11": "Fundo de Fundos",
    }

    st.markdown("---")
    st.subheader("Configurar Carteira para Análise")
    rc1, rc2 = st.columns([2, 1])
    with rc1:
        tickers_input = st.text_input(
            "Tickers (separados por vírgula)",
            value="MXRF11, HGLG11, KNCR11, XPLG11",
            help="Insira os tickers dos FIIs da sua carteira.",
        )
    with rc2:
        corr_threshold = st.slider(
            "Limiar de Alta Correlação", 0.50, 0.95, 0.75, step=0.05,
            help="Correlações acima deste valor serão destacadas como risco."
        )

    tickers_raw = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]

    if st.button("🔍 Analisar Correlações", type="primary", key="btn_corr"):
        with st.spinner("Calculando correlações..."):
            import random

            # Dados sintéticos realistas com correlações variadas
            def _corr_series(n: int, mu: float, sigma: float, seed: int) -> list[float]:
                random.seed(seed)
                return [random.gauss(mu, sigma) for _ in range(n)]

            N_MONTHS = 36
            seeds = {t: i * 17 + 3 for i, t in enumerate(tickers_raw)}

            # Introduzir correlação variada: pares de papel têm alta correlação
            return_series_corr: dict[str, list[float]] = {}
            for i, t in enumerate(tickers_raw):
                base_seed = seeds[t]
                sector = SECTOR_MAP_DEFAULT.get(t, "Outros")
                # Mesmo setor → retornos baseados em mesmo seed (correlação alta)
                if sector == "Papel (CRI)":
                    base = _corr_series(N_MONTHS, 0.007, 0.025, seed=1)
                elif sector == "Logística":
                    base = _corr_series(N_MONTHS, 0.008, 0.030, seed=2)
                elif sector == "Shopping":
                    base = _corr_series(N_MONTHS, 0.006, 0.035, seed=3)
                else:
                    base = _corr_series(N_MONTHS, 0.007, 0.028, seed=base_seed)
                # Adicionar ruído idiossincrático
                noise = _corr_series(N_MONTHS, 0.0, 0.015, seed=base_seed)
                return_series_corr[t] = [b * 0.7 + n * 0.3 for b, n in zip(base, noise)]

            portfolio_corr = [
                {"ticker": t, "quantidade": max(1, 100 - i * 15), "preco_atual": 10.0 + i * 30}
                for i, t in enumerate(tickers_raw)
            ]

            analysis = analyse_portfolio_risk(
                portfolio=portfolio_corr,
                return_series=return_series_corr,
                sector_map=SECTOR_MAP_DEFAULT,
                high_corr_threshold=corr_threshold,
            )

        # ── Métricas principais ──
        st.success("Análise concluída!")
        am1, am2, am3 = st.columns(3)
        am1.metric("📊 Volatilidade Anual do Portfólio",
                   f"{analysis['portfolio_annual_volatility']*100:.2f}%")
        am2.metric("🔀 Diversification Ratio",
                   f"{analysis['diversification_ratio']:.2f}",
                   delta="Bom" if analysis['diversification_ratio'] > 1.2 else "Baixo",
                   delta_color="normal" if analysis['diversification_ratio'] > 1.2 else "inverse")
        am3.metric("🏗️ Concentração (HHI)",
                   f"{analysis['herfindahl_index']:.2f}",
                   delta=analysis['concentration_risk'])

        # ── Alertas ──
        if analysis["warnings"]:
            st.markdown("---")
            st.subheader("⚠️ Alertas Automáticos")
            for w in analysis["warnings"]:
                st.warning(w)

        st.markdown("---")

        # ── Heatmap de Correlação ──
        col_h1, col_h2 = st.columns([3, 2])
        with col_h1:
            st.subheader("Heatmap de Correlação")
            matrix = analysis["correlation_matrix"]
            tickers_in_matrix = list(matrix.keys())
            df_corr = pd.DataFrame(
                [[matrix[t1][t2] for t2 in tickers_in_matrix] for t1 in tickers_in_matrix],
                index=tickers_in_matrix,
                columns=tickers_in_matrix,
            )
            fig_h, ax_h = plt.subplots(figsize=(max(5, len(tickers_in_matrix) * 1.2),
                                                max(4, len(tickers_in_matrix) * 1.0)))
            sns.heatmap(
                df_corr, annot=True, fmt=".2f", cmap="RdYlGn_r",
                center=0, vmin=-1, vmax=1, square=True,
                linewidths=0.5, ax=ax_h,
                cbar_kws={"shrink": 0.8},
            )
            ax_h.set_title("Correlação de Pearson (36 meses)", fontsize=11)
            plt.tight_layout()
            st.pyplot(fig_h)

        # ── Concentração Setorial ──
        with col_h2:
            st.subheader("Concentração Setorial")
            sector_data = analysis["sector_concentration"]
            if sector_data:
                df_sector = pd.DataFrame({
                    "Setor": list(sector_data.keys()),
                    "Alocação (%)": [v * 100 for v in sector_data.values()],
                })
                fig_s, ax_s = plt.subplots(figsize=(5, 4))
                colors = ["#4CAF50", "#2196F3", "#FF9800", "#9C27B0", "#F44336", "#607D8B"]
                ax_s.pie(
                    df_sector["Alocação (%)"],
                    labels=df_sector["Setor"],
                    autopct="%1.1f%%",
                    colors=colors[:len(df_sector)],
                    startangle=90,
                )
                ax_s.set_title(f"HHI: {analysis['herfindahl_index']:.2f} ({analysis['concentration_risk']})")
                st.pyplot(fig_s)

        # ── Pares de alta correlação ──
        if analysis["high_correlation_pairs"]:
            st.markdown("---")
            st.subheader(f"🔴 Pares com Correlação > {corr_threshold}")
            df_pairs = pd.DataFrame(analysis["high_correlation_pairs"])
            df_pairs = df_pairs.rename(columns={
                "ticker_a": "Ativo A", "ticker_b": "Ativo B",
                "correlation": "Correlação", "classification": "Classificação"
            })
            st.dataframe(df_pairs, use_container_width=True, hide_index=True)
            st.info(
                "💡 Pares com alta correlação se movem juntos. "
                "Ter ambos na carteira **não** reduz o risco — "
                "considere substitui-los por ativos de setores diferentes."
            )
        else:
            st.success(f"✅ Nenhum par com correlação acima de {corr_threshold}. Boa diversificação!")

    else:
        st.markdown("""
        ### Por que correlação importa?

        | Conceito | O que significa |
        |---|---|
        | **Correlação 1.0** | Os dois ativos sempre sobem e caem juntos — diversificação zero |
        | **Correlação 0.0** | Movimentos independentes — diversificação máxima |
        | **Correlação -1.0** | Um sobe quando o outro cai — hedge perfeito |
        | **HHI (Herfindahl)** | < 0.15 = diversificado; > 0.40 = concentrado demais |
        | **Diversification Ratio** | > 1.2 = portfólio aproveita a diversificação real |

        Insira sua carteira acima e clique em **Analisar Correlações**.
        """)


# ===========================================================================
# ABA 4 — MARKOWITZ: FRONTEIRA EFICIENTE
# ===========================================================================
with tab_markowitz:
    st.header("🔷 Markowitz — Fronteira Eficiente")
    st.markdown(
        "Simula milhares de combinações de pesos e encontra a **carteira ótima** "
        "que maximiza o Sharpe ou minimiza a volatilidade."
    )

    st.info(
        "🧠 **Sem PyPortfolioOpt.** Implementação própria em Python puro usando "
        "Monte Carlo de pesos (3 000 portfólios simulados)."
    )

    st.markdown("---")
    mk1, mk2, mk3 = st.columns(3)
    with mk1:
        mk_tickers_input = st.text_input(
            "Tickers para otimizar",
            value="MXRF11, HGLG11, KNCR11, XPLG11",
            key="mk_tickers",
        )
    with mk2:
        mk_n_sim = st.slider("Portfólios Simulados", 500, 5000, 2000, step=500, key="mk_nsim")
    with mk3:
        mk_rf = st.number_input("Taxa Livre de Risco (%/ano)", value=10.75, step=0.25) / 100.0

    mk_tickers = [t.strip().upper() for t in mk_tickers_input.split(",") if t.strip()]

    mk_col_w1, mk_col_w2 = st.columns(2)
    with mk_col_w1:
        mk_min_w = st.slider("Peso Mínimo por Ativo (%)", 0, 20, 2, step=1) / 100.0
    with mk_col_w2:
        mk_max_w = st.slider("Peso Máximo por Ativo (%)", 25, 100, 50, step=5) / 100.0

    if st.button("⚙️ Otimizar Carteira", type="primary", key="btn_markowitz"):
        with st.spinner(f"Simulando {mk_n_sim:,} portfólios..."):
            import random as _rnd

            # Dados sintéticos com retornos variados por setor
            _MK_SECTOR_BASE = {
                "MXRF11": 7, "KNCR11": 7, "RECR11": 7, "MCCI11": 7, "VRTA11": 7,
                "HGLG11": 8, "XPLG11": 8, "BTLG11": 8,
                "XPML11": 6, "MALL11": 6, "VISC11": 6,
                "BRCR11": 5, "JSRE11": 5,
                "BCFF11": 7, "HFOF11": 7,
            }

            def _mk_returns(ticker: str, n: int = 36) -> list[float]:
                base_mu = _MK_SECTOR_BASE.get(ticker, 7) / 1000.0  # ex: 7 → 0.7%/mês
                _rnd.seed(hash(ticker) % 9999)
                sector_factor = _rnd.gauss(1.0, 0.10)
                returns = []
                for _ in range(n):
                    r = _rnd.gauss(base_mu * sector_factor, 0.025)
                    returns.append(r)
                return returns

            mk_return_series = {t: _mk_returns(t) for t in mk_tickers}
            mk_corr_matrix = build_correlation_matrix(mk_tickers, mk_return_series)

            result = compare_strategies(
                tickers=mk_tickers,
                return_series=mk_return_series,
                correlation_matrix=mk_corr_matrix,
                n_simulations=mk_n_sim,
                risk_free_rate=mk_rf,
                min_weight=mk_min_w,
                max_weight=mk_max_w,
                seed=42,
            )

        frontier = result["frontier"]
        ms  = result["max_sharpe"]
        mv  = result["min_volatility"]
        ew  = result["equal_weight"]

        st.success(f"Otimização concluída! {len(frontier):,} portfólios avaliados.")

        # ── Métricas top ──
        met1, met2, met3 = st.columns(3)
        met1.metric("🥇 Max Sharpe",
                    f"Sharpe {ms['sharpe']:.3f}",
                    delta=f"Ret {ms['return']*100:.2f}% | Vol {ms['volatility']*100:.2f}%")
        met2.metric("🛡️ Min Volatility",
                    f"Vol {mv['volatility']*100:.2f}%",
                    delta=f"Ret {mv['return']*100:.2f}% | Sharpe {mv['sharpe']:.3f}")
        met3.metric("⚖️ Equal Weight (base)",
                    f"Sharpe {ew['sharpe']:.3f}",
                    delta=f"Ret {ew['return']*100:.2f}% | Vol {ew['volatility']*100:.2f}%",
                    delta_color="off")

        st.markdown("---")

        # ── Scatter — Fronteira Eficiente ──
        st.subheader("Nuvem de Portfólios — Fronteira de Eficiência")

        vols_all    = [p["volatility"] * 100 for p in frontier]
        rets_all    = [p["return"]     * 100 for p in frontier]
        sharpes_all = [p["sharpe"]           for p in frontier]

        fig_mk, ax_mk = plt.subplots(figsize=(12, 6))
        sc = ax_mk.scatter(
            vols_all, rets_all,
            c=sharpes_all, cmap="RdYlGn",
            alpha=0.45, s=12, zorder=2,
        )
        plt.colorbar(sc, ax=ax_mk, label="Sharpe Ratio")

        # Marcar estratégias especiais
        for p, color, marker, label in [
            (ms, "#1565C0", "*", f"Max Sharpe ({ms['sharpe']:.2f})"),
            (mv, "#6A1B9A", "D", f"Min Volatility ({mv['volatility']*100:.1f}%)"),
            (ew, "#E65100", "P", f"Equal Weight ({ew['sharpe']:.2f})"),
        ]:
            ax_mk.scatter(
                p["volatility"] * 100, p["return"] * 100,
                color=color, marker=marker, s=250, zorder=5, label=label,
                edgecolors="white", linewidths=0.8,
            )

        ax_mk.set_xlabel("Volatilidade Anual (%)")
        ax_mk.set_ylabel("Retorno Esperado Anual (%)")
        ax_mk.set_title("Fronteira Eficiente de Markowitz (Monte Carlo de pesos)")
        ax_mk.legend(loc="upper left")
        ax_mk.grid(alpha=0.25)
        plt.tight_layout()
        st.pyplot(fig_mk)

        st.markdown("---")

        # ── Tabela comparativa ──
        st.subheader("Comparação das Estratégias")
        df_strat = pd.DataFrame({
            "Estratégia": ["Max Sharpe", "Min Volatility", "Equal Weight"],
            "Retorno a.a.": [f"{p['return']*100:.2f}%" for p in [ms, mv, ew]],
            "Volatilidade a.a.": [f"{p['volatility']*100:.2f}%" for p in [ms, mv, ew]],
            "Sharpe Ratio": [f"{p['sharpe']:.3f}" for p in [ms, mv, ew]],
        })
        st.dataframe(df_strat, use_container_width=True, hide_index=True)

        # ── Pesos por estratégia ──
        st.markdown("---")
        st.subheader("Distribuição de Pesos por Estratégia")
        pw1, pw2, pw3 = st.columns(3)

        def _pie_chart(strategy: dict, title: str, ax_target):
            weights = strategy.get("weights", {})
            labels = list(weights.keys())
            sizes  = [weights[t] * 100 for t in labels]
            colors = ["#4CAF50", "#2196F3", "#FF9800", "#9C27B0", "#F44336", "#607D8B"]
            ax_target.pie(sizes, labels=labels, autopct="%1.1f%%",
                          colors=colors[:len(labels)], startangle=90)
            ax_target.set_title(title, fontsize=9)

        fig_pw, axes = plt.subplots(1, 3, figsize=(12, 4))
        _pie_chart(ms, "Max Sharpe", axes[0])
        _pie_chart(mv, "Min Volatility", axes[1])
        _pie_chart(ew, "Equal Weight", axes[2])
        plt.tight_layout()
        st.pyplot(fig_pw)

        # ── Relatório ──
        with st.expander("📋 Relatório Completo"):
            st.code(format_strategy_report(result), language="")

    else:
        st.markdown("""
        ### Como funciona a Otimização de Markowitz

        | Conceito | Explicação |
        |---|---|
        | **Monte Carlo de Pesos** | Gera N combinações aleatórias de pesos e avalia cada uma |
        | **Max Sharpe** | Portfólio com melhor retorno ajustado ao risco |
        | **Min Volatility** | Portfólio mais estável, menor oscilação possível |
        | **Equal Weight** | Baseline ingênuo: todos os ativos com o mesmo peso |
        | **Fronteira Eficiente** | A "borda" superior do scatter: máximo retorno para cada nível de risco |

        Configure seus tickers, limites de peso e clique em **Otimizar Carteira**.
        """)


