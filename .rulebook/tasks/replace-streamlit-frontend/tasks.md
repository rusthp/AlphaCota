## 1. Research Phase
- [x] 1.1 Clone and analyze `git@github.com:rusthp/alpha-cota-insight.git`
- [x] 1.2 Document tech stack, component structure, and design patterns used
- [x] 1.3 Map current Streamlit dashboard features to API endpoints needed

**Stack:** React 18 + Vite 5 + TypeScript + shadcn/ui + Tailwind + Recharts + TanStack Query + React Router v6
**Design:** Dark-only fintech, glassmorphism, Space Grotesk + JetBrains Mono

## 2. API Expansion Phase
- [x] 2.1 Design REST API endpoints (24 endpoints total)
- [x] 2.2 Implement scanner endpoint (`GET /api/scanner`)
- [x] 2.3 Implement FII detail endpoint (`GET /api/fii/:ticker`)
- [x] 2.4 Implement correlation endpoint (`POST /api/correlation`)
- [x] 2.5 Implement stress test endpoint (`POST /api/stress`)
- [x] 2.6 Implement macro endpoint (`GET /api/macro`)
- [x] 2.7 Implement momentum/cluster endpoints (`GET /api/momentum`, `GET /api/clusters`)
- [x] 2.8 Implement AI insights endpoint (`POST /api/ai/analyze`)
- [x] 2.9 Implement simulate/monte-carlo endpoints (`POST /api/simulate`, `POST /api/monte-carlo`)
- [x] 2.10 Implement FIRE endpoint (`POST /api/fire`)
- [x] 2.11 Implement news endpoint (`GET /api/news/:ticker`)
- [x] 2.12 Implement universe endpoint (`GET /api/universe`)
- [x] 2.13 Implement market news endpoint (`GET /api/news`)
- [x] 2.14 Implement data sources endpoint (`GET /api/sources`)
- [x] 2.15 Implement report endpoints (`GET /api/report/tearsheet`, `GET /api/report/csv`)

## 3. Frontend Integration Phase
- [x] 3.1 Copy reference repo into `frontend/`, remove Lovable branding
- [x] 3.2 Create API service layer (`src/services/api.ts`) + TanStack Query hooks (`src/hooks/use-api.ts`)
- [x] 3.3 ScannerPage: real API data + favoritos com localStorage
- [x] 3.4 FIIDetailPage: real fundamentals, preco, score, noticias RSS
- [x] 3.5 PortfolioPage: editavel (add/remove/edit FIIs), perfil de investidor, alocacao por segmento
- [x] 3.6 SimulatorPage: auto-preenche com carteira real do usuario
- [x] 3.7 AIInsightsPage: real Groq/Llama + noticias RSS (Live Mode)
- [x] 3.8 Vite proxy config + CORS middleware
- [x] 3.9 `start.py` — script unico para subir backend + frontend
- [x] 3.10 MacroPage: dashboard macro com Selic/CDI/IPCA do BCB
- [x] 3.11 MomentumPage: ranking de momentum com retornos 3M/6M/12M
- [x] 3.12 StressPage: stress test interativo usando carteira
- [x] 3.13 CorrelationPage: heatmap de correlacao com insights
- [x] 3.14 ClustersPage: visualizacao K-Means com cluster cards

## 4. Migration Phase
- [x] 4.1 Feature parity verification against Streamlit dashboard
- [ ] 4.2 Deprecate `frontend/dashboard.py`
- [ ] 4.3 Update documentation and README
