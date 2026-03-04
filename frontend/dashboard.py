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
st.sidebar.caption("AlphaCota v2 · Fase 1 ✅")

# ---------------------------------------------------------------------------
# Abas principais
# ---------------------------------------------------------------------------
tab_projecao, tab_backtest = st.tabs([
    "📈 Projeção Futura (Monte Carlo)",
    "🔬 Evidência Histórica (Backtest)",
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
