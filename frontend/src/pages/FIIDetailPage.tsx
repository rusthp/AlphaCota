import { useParams, Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  ArrowLeft, TrendingUp, DollarSign,
  BarChart3, Target, Loader2
} from "lucide-react";
import { useFIIDetail, useNews } from "@/hooks/use-api";

export default function FIIDetailPage() {
  const { ticker } = useParams<{ ticker: string }>();
  const { data: fii, isLoading, error } = useFIIDetail(ticker ?? "");
  const { data: newsData } = useNews(ticker ?? "");

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
      <div className="p-6 text-center text-destructive">
        <p className="text-lg font-semibold">Erro ao carregar {ticker}</p>
        <p className="text-sm text-muted-foreground mt-1">{(error as Error)?.message}</p>
      </div>
    );
  }

  const fund = fii.fundamentals as Record<string, number>;
  const evaluation = fii.evaluation as Record<string, number | string>;
  const score = Number(evaluation.score_final || 0);
  const scoreColor = score >= 85 ? "text-primary" : score >= 70 ? "text-accent" : "text-muted-foreground";
  const scoreLabel = score >= 85 ? "Excelente" : score >= 70 ? "Bom" : "Regular";

  const indicators = [
    { label: "Dividend Yield (12M)", value: `${((fund.dividend_yield || 0) * 100).toFixed(1)}%`, status: (fund.dividend_yield || 0) >= 0.07 ? "good" : "neutral" },
    { label: "P/VP", value: (fund.pvp || 0).toFixed(2), status: (fund.pvp || 1) <= 1.0 ? "good" : "neutral" },
    { label: "Vacância", value: `${((fund.vacancia || 0) * 100).toFixed(1)}%`, status: (fund.vacancia || 0) <= 0.1 ? "good" : "bad" },
    { label: "Preço Atual", value: `R$ ${fii.price.toFixed(2)}`, status: "good" },
    { label: "Dividendo/mês", value: `R$ ${fii.dividend_monthly.toFixed(2)}`, status: "good" },
    { label: "Fonte Preço", value: fii.price_source, status: "neutral" },
  ];

  return (
    <div className="space-y-6">
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
          </div>
          <p className="text-muted-foreground text-sm mt-1">Dados reais via {fii.price_source} + StatusInvest</p>
        </div>
      </div>

      {/* Price + Key Metrics */}
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
              {score.toFixed(0)}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Score + Label */}
      <Card className="bg-card border-border/30">
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-[family-name:var(--font-display)]">Score de Qualidade</CardTitle>
          <CardDescription>
            <span className={`font-bold ${scoreColor}`}>{score.toFixed(0)}</span>/100 — {scoreLabel}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Progress value={score} className="h-3" />
          {evaluation.risco_falencia && (
            <p className="text-xs text-muted-foreground mt-2">
              Risco Falência (Altman Z): <span className="font-mono">{String(evaluation.risco_falencia)}</span>
            </p>
          )}
        </CardContent>
      </Card>

      {/* Indicators Grid */}
      <Card className="bg-card border-border/30">
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-[family-name:var(--font-display)]">Indicadores Fundamentalistas</CardTitle>
        </CardHeader>
        <CardContent>
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
    </div>
  );
}
