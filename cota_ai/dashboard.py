import streamlit as st
import sqlite3
import pandas as pd
import json
import db
import main # Importamos o motor do scraper para adicionar FIIs na hora
import profile_logic

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="AlphaCota | Dashboard FII", layout="wide", page_icon="📈")

# Estilo customizado (CSS) para deixar mais premium
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #161b22; padding: 15px; border-radius: 10px; border: 1px solid #30363d; }
    </style>
""", unsafe_allow_html=True)

def carregar_dados_completos():
    conn = sqlite3.connect('meus_investimentos.db')
    query = "SELECT ticker, asset_type, metrics_data, last_updated FROM assets"
    df = pd.read_sql_query(query, conn)
    
    portfolio = db.buscar_portfolio()
    conn.close()
    
    if df.empty: return pd.DataFrame()

    metrics_list = []
    for m in df['metrics_data']:
        metrics_list.append(json.loads(m))
    
    metrics_df = pd.DataFrame(metrics_list)
    final_df = pd.concat([df[['ticker', 'last_updated']], metrics_df], axis=1)
    final_df['quantidade'] = final_df['ticker'].map(portfolio).fillna(0).astype(int)
    
    return final_df

# --- SIDEBAR (CONTROLES) ---
st.sidebar.header("🕹️ Gestão de Ativos")

# Seletor de Perfil
perfil_idx = ["Iniciante", "Mediano", "Agressivo", "Inteligente (Graham)"]
perfil_selecionado = st.sidebar.selectbox("👤 Seu Perfil de Investidor:", options=perfil_idx, index=1)

# Mensagem rápida de perfil
perfil_emoji = {"Iniciante": "🟢", "Mediano": "🟡", "Agressivo": "🔴", "Inteligente (Graham)": "🧠"}
st.sidebar.markdown(f"**Modo {perfil_emoji[perfil_selecionado]} {perfil_selecionado} Ativado**")

# 1. Adicionar Novo FII
with st.sidebar.expander("➕ Adicionar Novo FII", expanded=False):
    novo_ticker = st.text_input("Digite o Ticker (ex: XPML11):").upper().strip()
    col_add1, col_add2 = st.columns(2)
    
    if col_add1.button("Buscar Market"):
        if novo_ticker:
            with st.spinner(f"Catalogando {novo_ticker}..."):
                try:
                    dados = main.analisar_fii(novo_ticker)
                    if dados:
                        db.salvar_ativo(novo_ticker, "FII", dados)
                        st.sidebar.success(f"✅ {novo_ticker} Catalogado!")
                        st.rerun()
                    else:
                        st.sidebar.error("⚠️ Scraper falhou.")
                        st.session_state['manual_ticker'] = novo_ticker
                except Exception as e:
                    st.sidebar.error(f"Erro: {e}")
        else:
            st.sidebar.warning("Digite um ticker.")

    if st.session_state.get('manual_ticker') == novo_ticker:
        st.info("Deseja adicionar manualmente?")
        p_vp_manual = st.number_input("P/VP:", value=1.0)
        dy_manual = st.number_input("DY %:", value=10.0)
        preco_manual = st.number_input("Preço R$:", value=100.0)
        if st.button("Forçar Adição ✅"):
            dados_manuais = {
                "cotacao_atual": preco_manual,
                "dividend_yield": dy_manual,
                "p_vp": p_vp_manual,
                "fonte": "Manual"
            }
            db.salvar_ativo(novo_ticker, "FII", dados_manuais)
            st.rerun()

# 2. Remover Ativo
with st.sidebar.expander("🗑️ Remover Ativo", expanded=False):
    tickers_atuais = db.buscar_todos_tickers()
    fii_remover = st.selectbox("Escolha para remover:", options=tickers_atuais if tickers_atuais else ["Nenhum"])
    if st.button("Confirmar Exclusão"):
        if fii_remover != "Nenhum":
            db.deletar_ativo(fii_remover)
            st.sidebar.warning(f"{fii_remover} removido.")
            st.rerun()

st.sidebar.divider()
st.sidebar.divider()
if st.sidebar.button("🔍 Escanear Mercado (B3)"):
    st.info("Iniciando Escaneamento... Olhe o terminal para detalhes.")
    try:
        print("\n[DEBUG] Botão de Scan pressionado.")
        meta_ativos = main.escanear_mercado_statusinvest()
        
        if meta_ativos:
            print(f"[DEBUG] {len(meta_ativos)} ativos recebidos. Iniciando salvamento.")
            progresso = st.progress(0, text="Iniciando catálogo...")
            for i, item in enumerate(meta_ativos):
                ticker = item['ticker']
                metrics = item['metrics']
                db.salvar_ativo(ticker, "FII", metrics)
                
                percentual = (i + 1) / len(meta_ativos)
                if i % 10 == 0: # Atualiza a UI a cada 10 para performance
                    progresso.progress(percentual, text=f"Catalogando {ticker} ({i+1}/{len(meta_ativos)})")
            
            st.success(f"🏁 {len(meta_ativos)} FIIs catalogados!")
            print("[DEBUG] Scan concluído com sucesso.")
            st.rerun()
        else:
            st.error("Nenhum dado retornado da API.")
            print("[DEBUG] Falha: meta_ativos está vazio.")
    except Exception as e:
        st.error(f"Erro fatal no scan: {e}")
        print(f"[DEBUG] EXCEÇÃO: {e}")

st.sidebar.divider()
if st.sidebar.button("🔄 Atualizar Atuais (Scraper)"):
    with st.spinner("Atualizando preços..."):
        main.rodar_atualizacao_completa()
        st.rerun()
# --- TÍTULO PRINCIPAL ---
st.title("📈 AlphaCota - Intelligence Dashboard")

# Carregar dados
data = carregar_dados_completos()

if data.empty:
    st.info("👋 Bem-vindo! Comece adicionando um FII na barra lateral ao lado.")
    st.stop()

# --- ABAS PRINCIPAIS ---
tab_radar, tab_carteira, tab_ia = st.tabs(["📊 Radar de Mercado", "💼 Minha Carteira", "🧠 Cérebro IA"])

# --- ABA 1: RADAR DE MERCADO ---
with tab_radar:
    # Métricas de resumo rápido
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Ativos Monitorados", len(data))
    with col2:
        st.metric("P/VP Médio", f"{data['p_vp'].mean():.2f}")
    with col3:
        st.metric("DY Médio (12m)", f"{data['dividend_yield'].mean():.2f}%")

    st.divider()
    st.subheader(f"💎 Top Picks: Perfil {perfil_selecionado}")
    picks = profile_logic.get_top_picks(data, perfil_selecionado)
    
    if picks:
        cols_picks = st.columns(len(picks))
        for idx, pick in enumerate(picks):
            with cols_picks[idx]:
                container = st.container(border=True)
                container.markdown(f"### {pick['ticker']}")
                container.write(f"**P/VP:** {pick['pvp']:.2f}")
                container.write(f"**DY:** {pick['dy']:.2f}%")
                container.caption(f"_{pick['justificativa']}_")
    else:
        st.write("Nenhuma recomendação forte para este perfil no momento.")

    st.divider()
    st.subheader("🕵️ Radar de Oportunidades (Market Catalyst)")
    st.write("Aqui estão os FIIs catalogados com destaques automáticos. Filtrado por P/VP crescente.")
    
    # Ordena por P/VP para mostrar as melhores oportunidades no topo
    # Filtramos p_vp > 0.1 para evitar ativos com dados incompletos/lixo no topo
    data_radar = data[data['p_vp'] > 0.1][['ticker', 'cotacao_atual', 'p_vp', 'dividend_yield', 'last_updated']].sort_values('p_vp')

    st.dataframe(
        data_radar,
        column_config={
            "ticker": "Ticker",
            "cotacao_atual": st.column_config.NumberColumn("Preço Atual", format="R$ %.2f"),
            "p_vp": st.column_config.NumberColumn("P/VP", format="%.2f"),
            "dividend_yield": st.column_config.NumberColumn("DY (%)", format="%.2f%%"),
            "last_updated": "Última Atualização"
        },
        width="stretch",
        hide_index=True
    )

    st.subheader("📊 Valuation Master (P/VP)")
    import altair as alt

    # Preparar dados para o gráfico
    # Criar uma coluna de cor baseada no P/VP
    data['Valuation'] = data['p_vp'].apply(lambda x: 'Barato' if x <= 1.0 else 'Caro')
    
    chart = alt.Chart(data).mark_bar().encode(
        x=alt.X('ticker:N', title='FII'),
        y=alt.Y('p_vp:Q', title='P/VP'),
        color=alt.Color('Valuation:N', scale=alt.Scale(domain=['Barato', 'Caro'], range=['#2ecc71', '#e74c3c'])),
        tooltip=['ticker', 'p_vp', 'cotacao_atual']
    ).properties(height=400)

    # Linha de referência no 1.0
    rule = alt.Chart(pd.DataFrame({'y': [1.0]})).mark_rule(strokeDash=[5, 5], color='white').encode(y='y:Q')

    st.altair_chart(chart + rule, width="stretch")

# --- ABA 2: MINHA CARTEIRA ---
with tab_carteira:
    # Cálculos da Carteira
    data['renda_mensal'] = data['quantidade'] * (data['cotacao_atual'] * (data['dividend_yield'] / 100) / 12)
    total_renda = data['renda_mensal'].sum()
    
    col_met1, col_chart1 = st.columns([1, 2])
    with col_met1:
        st.metric("💸 Renda Mensal Estimada", f"R$ {total_renda:,.2f}")
    
    with col_chart1:
        # Gráfico de Rosca: Distribuição da Renda
        if total_renda > 0:
            renda_chart = alt.Chart(data[data['renda_mensal'] > 0]).mark_arc(innerRadius=50).encode(
                theta=alt.Theta(field="renda_mensal", type="quantitative"),
                color=alt.Color(field="ticker", type="nominal", title="Ativo"),
                tooltip=['ticker', 'renda_mensal']
            ).properties(height=200)
            st.altair_chart(renda_chart, width="stretch")
    
    st.subheader("💼 Posições Atuais")
    df_editor = data[['ticker', 'quantidade', 'cotacao_atual', 'dividend_yield']].copy()
    df_editor.columns = ['Ticker', 'Minha Qtd.', 'Preço Atual', 'DY (%)']
    
    edited_df = st.data_editor(
        df_editor,
        column_config={
            "Ticker": st.column_config.TextColumn(disabled=True),
            "Minha Qtd.": st.column_config.NumberColumn(min_value=0, step=1),
            "Preço Atual": st.column_config.NumberColumn(format="R$ %.2f", disabled=True),
            "DY (%)": st.column_config.NumberColumn(format="%.2f%%", disabled=True),
        },
        width="stretch",
        hide_index=True,
        key="portfolio_editor_tabs"
    )

    # Salvamento do editor
    if st.session_state.get("portfolio_editor_tabs") and "edited_rows" in st.session_state.portfolio_editor_tabs:
        for idx, updates in st.session_state.portfolio_editor_tabs["edited_rows"].items():
            if "Minha Qtd." in updates:
                ticker = df_editor.iloc[idx]['Ticker']
                db.salvar_posicao(ticker, updates["Minha Qtd."])
        st.rerun()

    st.divider()
    st.subheader("❄️ O Caminho da Liberdade (Loop Infinito)")
    st.write("O 'Loop Infinito' acontece quando o dividendo mensal de um FII é suficiente para comprar uma nova cota dele mesmo sem você colocar nenhum real a mais.")
    
    # Cálculos avançados do Loop Infinito
    data['div_mensal_unidade'] = (data['cotacao_atual'] * (data['dividend_yield'] / 100)) / 12
    data['renda_atual_ativo'] = data['quantidade'] * data['div_mensal_unidade']
    
    for _, row in data[data['quantidade'] > 0].iterrows():
        ticker = row['ticker']
        renda_atual = row['renda_atual_ativo']
        preco_cota = row['cotacao_atual']
        
        # Progresso do Loop (0 a 100%)
        progresso_loop = min(renda_atual / preco_cota, 1.0)
        
        col_l1, col_l2 = st.columns([3, 1])
        with col_l1:
            st.write(f"**{ticker}**")
            st.progress(progresso_loop, text=f"{progresso_loop*100:.1f}% para o Loop Infinito")
        with col_l2:
            faltam_cotas = int((preco_cota - renda_atual) / row['div_mensal_unidade']) if row['div_mensal_unidade'] > 0 else 0
            if progresso_loop >= 1.0:
                st.success("🔄 EM LOOP!")
            else:
                st.metric("Faltam Cotas", f"{faltam_cotas}")
    
    # Mentor Automatizado (Storytelling)
    st.divider()
    st.subheader("👨‍🏫 Mentoria Alpha")
    if perfil_selecionado == "Iniciante":
        st.info("💡 **Dica Iniciante:** Foque em ativos com DY estável. O segredo não é a velocidade, é o aporte constante. Seu objetivo atual: Completar seu primeiro 'Loop Infinito'.")
    elif perfil_selecionado == "Inteligente (Graham)":
        if data['p_vp'].mean() > 1.0:
            st.warning("🧐 **Dica Inteligente:** Seu P/VP médio está acima de 1.0. Para um seguidor de Graham, isso significa que você está pagando ágio. Busque oportunidades no Radar com P/VP < 0.9.")
        else:
            st.success("🎯 **Dica Inteligente:** Ótimo trabalho! Seu portfólio mantém uma margem de segurança saudável.")
    elif perfil_selecionado == "Agressivo":
        st.error("🔥 **Dica Agressiva:** Você está caçando yield! Certifique-se de que a vacância desses fundos não está subindo. O risco é seu combustível, mas não deixe o motor explodir.")

# --- ABA 3: CÉREBRO IA ---
with tab_ia:
    import news_scraper
    import ai_service
    
    st.subheader("🧠 Análise de Notícias & Insights")
    fii_ia = st.selectbox("Escolha o FII para análise profunda:", options=data['ticker'].unique())

    if st.button(f"Gerar Insight Groq sobre {fii_ia} 🪄"):
        insight_cache = db.buscar_insight_recente(fii_ia)
        if insight_cache:
            st.info("🕒 **Insight em Cache (gerado hoje):**")
            st.markdown(insight_cache)
        else:
            with st.spinner(f"Consultando Groq para {fii_ia}..."):
                noticias = news_scraper.buscar_noticias_fii(fii_ia)
                if noticias:
                    parecer = ai_service.analisar_com_groq(fii_ia, noticias)
                    db.salvar_insight(fii_ia, parecer)
                    st.markdown(parecer)
                    with st.expander("Fontes das Notícias"):
                        for n in noticias: st.write(f"- [{n['titulo']}]({n['link']})")
                else:
                    st.warning("Sem notícias recentes.")
