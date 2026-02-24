# 📈 AlphaCota - Intelligence Dashboard

AlphaCota é um dashboard inteligente para análise e gestão de Fundos Imobiliários (FIIs), utilizando o modelo **Llama 3 (Groq)** para insights de mercado e um sistema de **Market Scanner** para detecção automática de oportunidades.

## 🚀 Funcionalidades

- **🕵️ Market Scanner**: Catalogação em massa de centenas de FIIs da B3 em segundos via API.
- **🧠 Cérebro IA (Groq)**: Consultoria automatizada usando IA para análise de notícias de mercado.
- **❄️ Loop Infinito (Storytelling)**: Rastreador visual do efeito "Bola de Neve", mostrando o progresso até o reinvestimento automático.
- **👤 Perfis de Investidor**: Recomendações personalizadas (Iniciante, Mediano, Agressivo, Inteligente/Graham).
- **📊 Valuation Master**: Gráficos interativos interativos com sinalização de segurança (P/VP).
- **🛡️ AI Cache (FinOps)**: Sistema de economia de tokens com cache local de insights.

## 🛠️ Tecnologias

- **Python 3.12**
- **Streamlit** (Interface)
- **SQLite** (Banco de dados local)
- **Groq API** (Llama 3)
- **BeautifulSoup4 / Requests** (Engenharia de Scraper)

## 📦 Como Rodar

1. Clone o repositório:
   ```bash
   git clone git@github.com:rusthp/AlphaCota.git
   ```
2. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```
3. Configure seu `.env` com a `GROQ_API_KEY`.
4. Procure o dashboard:
   ```bash
   streamlit run dashboard.py
   ```

---
*Desenvolvido para transformar dados frios em decisões inteligentes.*
