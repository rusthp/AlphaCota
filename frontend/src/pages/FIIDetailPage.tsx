import { useParams, Link, useNavigate } from "react-router-dom";
import { useState, useEffect, useMemo, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  ArrowLeft, TrendingUp, DollarSign,
  BarChart3, Target, Loader2, Star, Building2, Users, Activity, GitCompareArrows, CalendarClock,
  Sparkles, ThumbsUp, ThumbsDown, Minus,
} from "lucide-react";
import {
  AreaChart, Area, BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer
} from "recharts";
import { useFIIDetail, useNews, useScoreHistory } from "@/hooks/use-api";
import { fetchUpcomingDividends, fetchAIAnalysis, type UpcomingDividendEvent, type AIAnalysisResult } from "@/services/api";
import DeepAnalysisPanel from "@/components/DeepAnalysisPanel";

const FAV_KEY = "alphacota_favourites";

function getFavourites(): string[] {
  try { return JSON.parse(localStorage.getItem(FAV_KEY) || "[]"); } catch { return []; }
}

function toggleFavourite(ticker: string): boolean {
  const favs = getFavourites();
  const idx = favs.indexOf(ticker);
  if (idx >= 0) { favs.splice(idx, 1); } else { favs.push(ticker); }
  localStorage.setItem(FAV_KEY, JSON.stringify(favs));
  return idx < 0;
}

export default function FIIDetailPage() {
  const { ticker } = useParams<{ ticker: string }>();
  const navigate = useNavigate();
  const { data: fii, isLoading, error } = useFIIDetail(ticker ?? "");
  const { data: newsData } = useNews(ticker ?? "");
  const { data: scoreHistory } = useScoreHistory(ticker ?? "");
  const [isFav, setIsFav] = useState(false);
  const [nextDividend, setNextDividend] = useState<UpcomingDividendEvent | null>(null);
  const [aiResult, setAiResult] = useState<AIAnalysisResult | null>(null);
  const [aiLoading, setAiLoading] = useState(false);

  useEffect(() => {
    if (ticker) setIsFav(getFavourites().includes(ticker.toUpperCase()));
  }, [ticker]);

  useEffect(() => {
    if (!ticker) return;
    fetchUpcomingDividends(90, ticker.toUpperCase())
      .then(({ events }) => setNextDividend(events[0] ?? null))
      .catch(() => {});
  }, [ticker]);

  const runAI = useCallback(async () => {
    if (!ticker || aiLoading) return;
    setAiLoading(true);
    try {
      const result = await fetchAIAnalysis(ticker.toUpperCase());
      setAiResult(result);
    } catch {
      setAiResult({ success: false, ticker: ticker, error: "Erro ao conectar com a API de IA." });
    } finally {
      setAiLoading(false);
    }
  }, [ticker, aiLoading]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96 gap-3 text-muted-foreground">
        <Loader2 className="w-5 h-5 animate-spin" />
        Carregando {ticker}...
      </div>
    );
  }

  if (error || !fii) {
    return (
      <div className="p-6 max-w-7xl mx-auto text-center text-destructive">
        <p className="text-lg font-semibold">Erro ao carregar {ticker}</p>
        <p className="text-sm text-muted-foreground mt-1">{(error as Error)?.message}</p>
      </div>
    );
  }

  const fund = fii.fundamentals as Record<string, number>;
  const evaluation = fii.evaluation as Record<string, number | string>;
  const scoreBreakdown = (fii as any).score_breakdown as Record<string, number> | undefined;
  const priceHistory: { month: string; price: number }[] = (fii as any).price_history ?? [];
  const dividendHistory: { month: string; value: number }[] = (fii as any).dividend_history ?? [];
  const fundInfo: Record<string, string | number | null> = (fii as any).fund_info ?? {};

  const totalScore = scoreBreakdown?.total ?? Number(evaluation.score_final || 0);
  const scoreColor = totalScore >= 85 ? "text-primary" : totalScore >= 70 ? "text-accent" : "text-muted-foreground";
  const scoreLabel = totalScore >= 85 ? "Excelente" : totalScore >= 70 ? "Bom" : "Regular";

  const confidence = fii.data_confidence ?? 0;
  const confidenceLabel = confidence >= 80 ? "Alta" : confidence >= 50 ? "Média" : "Baixa";
  const confidenceColor =
    confidence >= 80
      ? "bg-accent/15 text-accent border-accent/30"
      : confidence >= 50
      ? "bg-yellow-500/15 text-yellow-500 border-yellow-500/30"
      : "bg-destructive/15 text-destructive border-destructive/30";

  // Chart period filter
  const PERIODS = [
    { label: "3M",  months: 3 },
    { label: "6M",  months: 6 },
    { label: "1A",  months: 12 },
    { label: "2A",  months: 24 },
  ] as const;
  type Period = typeof PERIODS[number]["label"];
  const [pricePeriod,   setPricePeriod]   = useState<Period>("1A");
  const [divPeriod,     setDivPeriod]     = useState<Period>("1A");

  const sliceByPeriod = <T,>(data: T[], months: number) => data.slice(-months);

  const priceFiltered   = useMemo(() => sliceByPeriod(priceHistory,    PERIODS.find(p => p.label === pricePeriod)!.months), [priceHistory,    pricePeriod]);
  const divFiltered     = useMemo(() => sliceByPeriod(dividendHistory,  PERIODS.find(p => p.label === divPeriod)!.months),   [dividendHistory,  divPeriod]);

  const indicators = [
    { label: "Dividend Yield (12M)", value: `${((fund.dividend_yield || 0) * 100).toFixed(1)}%`, status: (fund.dividend_yield || 0) >= 0.07 ? "good" : "neutral" },
    { label: "P/VP", value: (fund.pvp || 0).toFixed(2), status: (fund.pvp || 1) <= 1.0 ? "good" : "neutral" },
    { label: "Vacância", value: `${((fund.vacancia || 0) * 100).toFixed(1)}%`, status: (fund.vacancia || 0) <= 0.1 ? "good" : "bad" },
    { label: "Preço Atual", value: `R$ ${fii.price.toFixed(2)}`, status: "good" },
    { label: "Dividendo/mês", value: `R$ ${fii.dividend_monthly.toFixed(2)}`, status: "good" },
    { label: "Liquidez Diária", value: fund.liquidez_diaria ? `R$ ${(fund.liquidez_diaria / 1e6).toFixed(1)}M` : "—", status: "neutral" },
  ];

  const extraIndicators = [
    { label: "Cap Rate", value: (fii as any).cap_rate != null ? `${((fii as any).cap_rate * 100).toFixed(1)}%` : "—", icon: <Target className="w-3.5 h-3.5" /> },
    { label: "Volatilidade 30d", value: (fii as any).volatilidade_30d != null ? `${(fii as any).volatilidade_30d.toFixed(1)}%` : "—", icon: <Activity className="w-3.5 h-3.5" /> },
    { label: "Nº de Imóveis", value: (fii as any).num_imoveis ?? "—", icon: <Building2 className="w-3.5 h-3.5" /> },
    { label: "Nº de Locatários", value: (fii as any).num_locatarios ?? "—", icon: <Users className="w-3.5 h-3.5" /> },
  ];

  const scoreItems = scoreBreakdown
    ? [
        { label: "Fundamentos", value: scoreBreakdown.fundamentos, color: "bg-primary" },
        { label: "Rendimento", value: scoreBreakdown.rendimento, color: "bg-accent" },
        { label: "Risco", value: scoreBreakdown.risco, color: "bg-yellow-500" },
        { label: "Liquidez", value: scoreBreakdown.liquidez, color: "bg-blue-500" },
      ]
    : [];

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Back + Header */}
      <div className="flex items-start gap-4">
        <Link to="/dashboard/scanner">
          <Button variant="ghost" size="icon" className="mt-1">
            <ArrowLeft className="w-4 h-4" />
          </Button>
        </Link>
        <div className="flex-1">
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-2xl font-bold font-[family-name:var(--font-display)]">{fii.ticker}</h1>
            <Badge variant="outline" className="border-border/50">{fii.segment}</Badge>
            <Badge
              variant="outline"
              className={`text-xs border ${confidenceColor}`}
              title={`Confiança nos dados: ${confidence}%`}
            >
              Confiança: {confidenceLabel} ({confidence}%)
            </Badge>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setIsFav(toggleFavourite(fii.ticker))}
              title={isFav ? "Remover dos favoritos" : "Adicionar aos favoritos"}
            >
              <Star className={`w-4 h-4 ${isFav ? "fill-yellow-400 text-yellow-400" : "text-muted-foreground"}`} />
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => navigate(`/dashboard/compare?tickers=${fii.ticker}`)}
              title="Comparar com outros FIIs"
              className="border-border/50 hover:bg-secondary gap-1.5"
            >
              <GitCompareArrows className="w-3.5 h-3.5" />
              Comparar
            </Button>
          </div>
          <p className="text-muted-foreground text-sm mt-1">Dados reais via {fii.price_source} + CVM + FundsExplorer</p>
        </div>
      </div>

      {/* Next dividend banner */}
      {nextDividend && (
        <div className={`rounded-lg border p-3 flex items-center gap-3 text-sm ${
          nextDividend.days_to_pay <= 7
            ? "border-primary/50 bg-primary/5"
            : nextDividend.days_to_ex <= 3
            ? "border-yellow-500/50 bg-yellow-500/5"
            : "border-border/40 bg-secondary/40"
        }`}>
          <CalendarClock className={`w-4 h-4 shrink-0 ${nextDividend.days_to_pay <= 7 ? "text-primary" : "text-muted-foreground"}`} />
          <div className="flex flex-wrap gap-x-4 gap-y-0.5">
            {nextDividend.days_to_ex >= 0 && (
              <span>
                <span className="text-muted-foreground">Ex-dividendo: </span>
                <span className="font-medium font-mono">{nextDividend.ex_date}</span>
                <span className="text-muted-foreground ml-1">({nextDividend.days_to_ex}d)</span>
              </span>
            )}
            <span>
              <span className="text-muted-foreground">Pagamento: </span>
              <span className="font-medium font-mono">{nextDividend.pay_date}</span>
              <span className="text-muted-foreground ml-1">({nextDividend.days_to_pay}d)</span>
            </span>
            <span>
              <span className="text-muted-foreground">Valor: </span>
              <span className="font-bold font-mono text-accent">R$ {nextDividend.valor_por_cota.toFixed(4)}/cota</span>
            </span>
            {!nextDividend.confirmado && (
              <span className="text-xs text-muted-foreground italic">estimado</span>
            )}
          </div>
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card className="bg-card border-border/30">
          <CardContent className="p-4">
            <div className="flex items-center gap-1.5 text-muted-foreground text-xs mb-1">
              <DollarSign className="w-3.5 h-3.5" /> Preço
            </div>
            <p className="text-xl font-bold font-[family-name:var(--font-mono)]">R$ {fii.price.toFixed(2)}</p>
          </CardContent>
        </Card>
        <Card className="bg-card border-border/30">
          <CardContent className="p-4">
            <div className="flex items-center gap-1.5 text-muted-foreground text-xs mb-1">
              <TrendingUp className="w-3.5 h-3.5" /> DY (12M)
            </div>
            <p className="text-xl font-bold font-[family-name:var(--font-mono)] text-primary">
              {((fund.dividend_yield || 0) * 100).toFixed(1)}%
            </p>
          </CardContent>
        </Card>
        <Card className="bg-card border-border/30">
          <CardContent className="p-4">
            <div className="flex items-center gap-1.5 text-muted-foreground text-xs mb-1">
              <BarChart3 className="w-3.5 h-3.5" /> P/VP
            </div>
            <p className="text-xl font-bold font-[family-name:var(--font-mono)]">{(fund.pvp || 0).toFixed(2)}</p>
          </CardContent>
        </Card>
        <Card className="bg-card border-border/30">
          <CardContent className="p-4">
            <div className="flex items-center gap-1.5 text-muted-foreground text-xs mb-1">
              <Target className="w-3.5 h-3.5" /> Score
            </div>
            <p className={`text-xl font-bold font-[family-name:var(--font-mono)] ${scoreColor}`}>
              {totalScore.toFixed(0)}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Charts row */}
      {(priceHistory.length > 0 || dividendHistory.length > 0) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Price chart */}
          {priceHistory.length > 0 && (
            <Card className="bg-card border-border/30">
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base font-[family-name:var(--font-display)]">Histórico de Preços</CardTitle>
                  <div className="flex gap-1">
                    {PERIODS.map((p) => (
                      <button
                        key={p.label}
                        onClick={() => setPricePeriod(p.label)}
                        className={[
                          "px-2 py-0.5 rounded text-xs font-mono transition-colors",
                          pricePeriod === p.label
                            ? "bg-primary text-primary-foreground"
                            : "text-muted-foreground hover:bg-secondary",
                        ].join(" ")}
                      >
                        {p.label}
                      </button>
                    ))}
                  </div>
                </div>
                {priceFiltered.length > 0 && (
                  <CardDescription className="text-xs">
                    {priceFiltered[0].month} → {priceFiltered[priceFiltered.length - 1].month}
                    {" · "}
                    <span className={
                      priceFiltered[priceFiltered.length - 1].price >= priceFiltered[0].price
                        ? "text-primary" : "text-destructive"
                    }>
                      {((priceFiltered[priceFiltered.length - 1].price / priceFiltered[0].price - 1) * 100).toFixed(1)}%
                    </span>
                  </CardDescription>
                )}
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={180}>
                  <AreaChart data={priceFiltered} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} />
                    <XAxis dataKey="month" tick={{ fontSize: 10 }} stroke="hsl(var(--muted-foreground))" />
                    <YAxis tick={{ fontSize: 10 }} stroke="hsl(var(--muted-foreground))" domain={["auto", "auto"]} width={52} />
                    <Tooltip
                      contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 }}
                      formatter={(v: number) => [`R$ ${v.toFixed(2)}`, "Preço"]}
                    />
                    <Area type="monotone" dataKey="price" stroke="hsl(var(--primary))" fill="url(#priceGrad)" strokeWidth={2} dot={priceFiltered.length <= 6} />
                  </AreaChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}

          {/* Dividend chart */}
          {dividendHistory.length > 0 && (
            <Card className="bg-card border-border/30">
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base font-[family-name:var(--font-display)]">Dividendos por Cota</CardTitle>
                  <div className="flex gap-1">
                    {PERIODS.map((p) => (
                      <button
                        key={p.label}
                        onClick={() => setDivPeriod(p.label)}
                        className={[
                          "px-2 py-0.5 rounded text-xs font-mono transition-colors",
                          divPeriod === p.label
                            ? "bg-accent text-accent-foreground"
                            : "text-muted-foreground hover:bg-secondary",
                        ].join(" ")}
                      >
                        {p.label}
                      </button>
                    ))}
                  </div>
                </div>
                {divFiltered.length > 0 && (
                  <CardDescription className="text-xs">
                    Média: <span className="text-accent font-mono">
                      R$ {(divFiltered.reduce((s, d) => s + d.value, 0) / divFiltered.length).toFixed(4)}
                    </span>
                    {" · "}
                    Total: <span className="text-accent font-mono">
                      R$ {divFiltered.reduce((s, d) => s + d.value, 0).toFixed(2)}
                    </span>
                  </CardDescription>
                )}
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={180}>
                  <BarChart data={divFiltered} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} />
                    <XAxis dataKey="month" tick={{ fontSize: 10 }} stroke="hsl(var(--muted-foreground))" />
                    <YAxis tick={{ fontSize: 10 }} stroke="hsl(var(--muted-foreground))" width={48} />
                    <Tooltip
                      contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 }}
                      formatter={(v: number) => [`R$ ${v.toFixed(4)}`, "Dividendo"]}
                    />
                    <Bar dataKey="value" fill="hsl(var(--accent))" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* Score History chart */}
      {scoreHistory && scoreHistory.timeline && scoreHistory.timeline.length > 0 && (
        <Card className="bg-card border-border/30">
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-[family-name:var(--font-display)]">Evolução Histórica do Score (12M)</CardTitle>
            <CardDescription className="text-xs">Acompanhamento da qualidade do FII nos últimos meses.</CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={180}>
               <LineChart data={scoreHistory.timeline} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                 <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} />
                 <XAxis dataKey="date" tick={{ fontSize: 10 }} stroke="hsl(var(--muted-foreground))" />
                 <YAxis tick={{ fontSize: 10 }} stroke="hsl(var(--muted-foreground))" domain={[0, 100]} width={25} />
                 <Tooltip
                   contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 }}
                   formatter={(v: number) => [v.toFixed(1), "AlphaScore"]}
                 />
                 <Line type="monotone" dataKey="score" stroke="hsl(var(--primary))" strokeWidth={2} dot={{ r: 3 }} />
               </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* Score Breakdown */}
      {scoreItems.length > 0 && (
        <Card className="bg-card border-border/30">
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-[family-name:var(--font-display)]">Score de Qualidade FII</CardTitle>
            <CardDescription>
              <span className={`font-bold ${scoreColor}`}>{totalScore.toFixed(0)}</span>/100 — {scoreLabel}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {scoreItems.map((item) => (
              <div key={item.label}>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-muted-foreground">{item.label}</span>
                  <span className="font-mono font-bold">{item.value.toFixed(1)}/25</span>
                </div>
                <Progress value={(item.value / 25) * 100} className="h-2" />
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Extra Indicators */}
      <Card className="bg-card border-border/30">
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-[family-name:var(--font-display)]">Indicadores Avançados</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
            {extraIndicators.map((ind) => (
              <div key={ind.label} className="p-3 rounded-lg bg-secondary/50 border border-border/20">
                <div className="flex items-center gap-1.5 text-muted-foreground text-xs mb-1">
                  {ind.icon} {ind.label}
                </div>
                <p className="text-lg font-bold font-[family-name:var(--font-mono)]">{String(ind.value)}</p>
              </div>
            ))}
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
            {indicators.map((ind) => (
              <div key={ind.label} className="p-3 rounded-lg bg-secondary/50 border border-border/20">
                <p className="text-xs text-muted-foreground mb-1">{ind.label}</p>
                <p className={`text-lg font-bold font-[family-name:var(--font-mono)] ${
                  ind.status === "good" ? "text-accent" : ind.status === "bad" ? "text-destructive" : "text-foreground"
                }`}>
                  {ind.value}
                </p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Fund Info */}
      {Object.keys(fundInfo).length > 0 && (
        <Card className="bg-card border-border/30">
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-[family-name:var(--font-display)]">Informações do Fundo</CardTitle>
            {fundInfo.nome && (
              <CardDescription>{String(fundInfo.nome)}</CardDescription>
            )}
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {fundInfo.patrimonio_liquido != null && (
                <div className="p-3 rounded-lg bg-secondary/50 border border-border/20">
                  <p className="text-xs text-muted-foreground mb-1 flex items-center gap-1">
                    <DollarSign className="w-3 h-3" /> Patrimônio
                  </p>
                  <p className="text-sm font-mono font-bold">
                    R$ {(Number(fundInfo.patrimonio_liquido) / 1e6).toFixed(0)}M
                  </p>
                </div>
              )}
              {fundInfo.num_cotas != null && (
                <div className="p-3 rounded-lg bg-secondary/50 border border-border/20">
                  <p className="text-xs text-muted-foreground mb-1 flex items-center gap-1">
                    <Hash className="w-3 h-3" /> Cotas Emitidas
                  </p>
                  <p className="text-sm font-mono font-bold">
                    {Number(fundInfo.num_cotas).toLocaleString("pt-BR")}
                  </p>
                </div>
              )}
              {fundInfo.dividendo_anual_por_cota != null && (
                <div className="p-3 rounded-lg bg-secondary/50 border border-border/20">
                  <p className="text-xs text-muted-foreground mb-1 flex items-center gap-1">
                    <TrendingUp className="w-3 h-3" /> Dividendo Anual/Cota
                  </p>
                  <p className="text-sm font-mono font-bold text-primary">
                    R$ {Number(fundInfo.dividendo_anual_por_cota).toFixed(2)}
                  </p>
                </div>
              )}
              {fundInfo.dy_yfinance != null && (
                <div className="p-3 rounded-lg bg-secondary/50 border border-border/20">
                  <p className="text-xs text-muted-foreground mb-1 flex items-center gap-1">
                    <BarChart3 className="w-3 h-3" /> DY (Yahoo)
                  </p>
                  <p className="text-sm font-mono font-bold text-primary">
                    {Number(fundInfo.dy_yfinance).toFixed(2)}%
                  </p>
                </div>
              )}
              {fundInfo.gestora && (
                <div className="p-3 rounded-lg bg-secondary/50 border border-border/20">
                  <p className="text-xs text-muted-foreground mb-1 flex items-center gap-1">
                    <Building2 className="w-3 h-3" /> Gestora
                  </p>
                  <p className="text-sm font-medium truncate">{String(fundInfo.gestora)}</p>
                </div>
              )}
              {fundInfo.administrador && (
                <div className="p-3 rounded-lg bg-secondary/50 border border-border/20">
                  <p className="text-xs text-muted-foreground mb-1 flex items-center gap-1">
                    <Building2 className="w-3 h-3" /> Administrador
                  </p>
                  <p className="text-sm font-medium truncate">{String(fundInfo.administrador)}</p>
                </div>
              )}
              {fundInfo.cnpj && (
                <div className="p-3 rounded-lg bg-secondary/50 border border-border/20">
                  <p className="text-xs text-muted-foreground mb-1 flex items-center gap-1">
                    <Hash className="w-3 h-3" /> CNPJ
                  </p>
                  <p className="text-sm font-mono">{String(fundInfo.cnpj)}</p>
                </div>
              )}
              {fundInfo.num_cotistas != null && (
                <div className="p-3 rounded-lg bg-secondary/50 border border-border/20">
                  <p className="text-xs text-muted-foreground mb-1 flex items-center gap-1">
                    <Users className="w-3 h-3" /> Cotistas
                  </p>
                  <p className="text-sm font-mono font-bold">
                    {Number(fundInfo.num_cotistas).toLocaleString("pt-BR")}
                  </p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* News */}
      {newsData && newsData.news.length > 0 && (
        <Card className="bg-card border-border/30">
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-[family-name:var(--font-display)]">Notícias Recentes</CardTitle>
            <CardDescription>{newsData.count} notícias via RSS</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {newsData.news.map((n, i) => (
                <a
                  key={i}
                  href={n.link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block p-3 rounded-lg bg-secondary/30 border border-border/20 hover:bg-secondary/50 transition-colors"
                >
                  <p className="text-sm font-medium">{n.titulo}</p>
                  <p className="text-xs text-muted-foreground mt-1">{n.data}</p>
                </a>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Deep Multi-Agent Analysis */}
      <DeepAnalysisPanel ticker={fii.ticker} />

      {/* AI Analysis (sentimento simples) */}
      <Card className="bg-card border-border/30">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base font-[family-name:var(--font-display)] flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-primary" />
                Análise IA
              </CardTitle>
              <CardDescription>Sentimento de notícias via Groq LLM</CardDescription>
            </div>
            <Button
              size="sm"
              variant={aiResult ? "outline" : "default"}
              onClick={runAI}
              disabled={aiLoading}
              className="gap-1.5"
            >
              {aiLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
              {aiResult ? "Reanalisar" : "Analisar"}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {!aiResult && !aiLoading && (
            <p className="text-sm text-muted-foreground">
              Clique em "Analisar" para processar as notícias recentes do {ticker} com IA e obter um parecer de sentimento.
            </p>
          )}
          {aiLoading && (
            <div className="flex items-center gap-3 text-sm text-muted-foreground py-4">
              <Loader2 className="w-4 h-4 animate-spin text-primary" />
              Processando notícias com Groq LLM...
            </div>
          )}
          {aiResult && !aiLoading && (
            <div className="space-y-4">
              {aiResult.success && aiResult.raw_response ? (
                <>
                  {/* Sentiment badge */}
                  {(() => {
                    const text = aiResult.raw_response.toUpperCase();
                    const isPos = text.includes("POSITIV");
                    const isNeg = text.includes("NEGATIV");
                    return (
                      <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium border ${
                        isPos ? "bg-accent/10 border-accent/30 text-accent"
                              : isNeg ? "bg-destructive/10 border-destructive/30 text-destructive"
                              : "bg-secondary border-border/50 text-muted-foreground"
                      }`}>
                        {isPos ? <ThumbsUp className="w-4 h-4" /> : isNeg ? <ThumbsDown className="w-4 h-4" /> : <Minus className="w-4 h-4" />}
                        {isPos ? "Sentimento Positivo" : isNeg ? "Sentimento Negativo" : "Sentimento Neutro"}
                      </div>
                    );
                  })()}
                  {/* Full response */}
                  <div className="text-sm leading-relaxed whitespace-pre-wrap bg-secondary/30 rounded-lg p-4 border border-border/20">
                    {aiResult.raw_response}
                  </div>
                </>
              ) : (
                <p className="text-sm text-destructive">
                  {aiResult.error || "Erro na análise. Verifique se GROQ_API_KEY está configurada no .env."}
                </p>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
