import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { TrendingUp, TrendingDown, Loader2, Building2 } from "lucide-react";
import { useMacro } from "@/hooks/use-api";

export default function MacroPage() {
  const { data, isLoading, error } = useMacro();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96 gap-3 text-muted-foreground">
        <Loader2 className="w-5 h-5 animate-spin" />
        Carregando dados do BCB...
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 text-center text-destructive">
        <p>Erro ao carregar dados macro: {(error as Error).message}</p>
      </div>
    );
  }

  const indicators = [
    { label: "Selic (meta)", value: data?.selic, suffix: "% a.a.", source: data?.selic_source, color: "text-primary" },
    { label: "CDI", value: data?.cdi, suffix: "% a.a.", source: data?.cdi_source, color: "text-accent" },
    { label: "IPCA (12M)", value: data?.ipca, suffix: "%", source: data?.ipca_source, color: "text-yellow-400" },
  ];

  // Derive useful metrics
  const selic = Number(data?.selic || 0);
  const ipca = Number(data?.ipca || 0);
  const juroReal = selic > 0 && ipca > 0 ? ((1 + selic / 100) / (1 + ipca / 100) - 1) * 100 : 0;

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-3">
          <Building2 className="w-6 h-6 text-primary" />
          Painel Macroeconômico
        </h1>
        <p className="text-sm text-muted-foreground mt-1">Dados reais do Banco Central do Brasil (BCB/SGS)</p>
        <Badge variant="outline" className="mt-2 text-xs border-primary/30 text-primary">
          Live — BCB API
        </Badge>
      </div>

      {/* Main indicators */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {indicators.map((ind) => (
          <Card key={ind.label} className="bg-card border-border/30">
            <CardContent className="p-6 text-center">
              <p className="text-xs text-muted-foreground mb-2">{ind.label}</p>
              <p className={`text-3xl font-bold font-[family-name:var(--font-mono)] ${ind.color}`}>
                {ind.value != null ? Number(ind.value).toFixed(2) : "—"}{ind.suffix}
              </p>
              <p className="text-xs text-muted-foreground mt-2">Fonte: {ind.source || "BCB"}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Derived metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="bg-card border-border/30">
          <CardContent className="p-4">
            <p className="text-xs text-muted-foreground mb-1">Juro Real</p>
            <p className={`text-xl font-bold font-[family-name:var(--font-mono)] ${juroReal >= 0 ? "text-accent" : "text-destructive"}`}>
              {juroReal.toFixed(2)}% a.a.
            </p>
            <p className="text-xs text-muted-foreground mt-1">Selic - IPCA (Fisher)</p>
          </CardContent>
        </Card>
        <Card className="bg-card border-border/30">
          <CardContent className="p-4">
            <p className="text-xs text-muted-foreground mb-1">Spread FII vs Selic</p>
            <p className="text-xl font-bold font-[family-name:var(--font-mono)] text-primary">
              {selic > 0 ? `~${(9 - selic).toFixed(1)}%` : "—"}
            </p>
            <p className="text-xs text-muted-foreground mt-1">DY médio FIIs (~9%) - Selic</p>
          </CardContent>
        </Card>
        <Card className="bg-card border-border/30">
          <CardContent className="p-4">
            <p className="text-xs text-muted-foreground mb-1">Atratividade FIIs</p>
            <div className="flex items-center gap-2 mt-1">
              {selic <= 10 ? (
                <><TrendingUp className="w-5 h-5 text-accent" /><span className="text-accent font-bold">Alta</span></>
              ) : selic <= 13 ? (
                <><TrendingUp className="w-5 h-5 text-yellow-400" /><span className="text-yellow-400 font-bold">Moderada</span></>
              ) : (
                <><TrendingDown className="w-5 h-5 text-destructive" /><span className="text-destructive font-bold">Baixa</span></>
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-1">Selic alta compete com FIIs</p>
          </CardContent>
        </Card>
        <Card className="bg-card border-border/30">
          <CardContent className="p-4">
            <p className="text-xs text-muted-foreground mb-1">IPCA Acumulado</p>
            <p className={`text-xl font-bold font-[family-name:var(--font-mono)] ${ipca > 5 ? "text-destructive" : "text-accent"}`}>
              {ipca.toFixed(2)}%
            </p>
            <p className="text-xs text-muted-foreground mt-1">{ipca > 5 ? "Acima da meta (3%)" : "Dentro da meta"}</p>
          </CardContent>
        </Card>
      </div>

      {/* Explanation */}
      <Card className="bg-card border-border/30">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Como interpretar</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground space-y-2">
          <p><strong className="text-foreground">Selic alta</strong> = renda fixa mais atrativa, pressão negativa nas cotas de FIIs. Mas FIIs de papel (CRI) se beneficiam.</p>
          <p><strong className="text-foreground">IPCA alto</strong> = FIIs indexados ao IPCA distribuem mais. Porém, pode indicar aperto monetário futuro.</p>
          <p><strong className="text-foreground">Juro real positivo</strong> = ganho acima da inflação. Bom para investidores de longo prazo.</p>
        </CardContent>
      </Card>
    </div>
  );
}
