import { useState, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Loader2, Sparkles, ChevronDown, ChevronUp,
  TrendingUp, TrendingDown, Minus,
  ShieldCheck, ShieldAlert, Brain, Target,
} from "lucide-react";
import { fetchDeepAnalysis, type DeepAnalysisResult } from "@/services/api";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function riskColor(nivel: string) {
  if (nivel === "baixo") return "text-accent border-accent/30 bg-accent/10";
  if (nivel === "medio") return "text-yellow-400 border-yellow-400/30 bg-yellow-400/10";
  if (nivel === "alto") return "text-orange-400 border-orange-400/30 bg-orange-400/10";
  return "text-destructive border-destructive/30 bg-destructive/10";
}

function opiniaoColor(op: string) {
  if (op === "comprar") return "text-accent border-accent/30 bg-accent/10";
  if (op === "evitar") return "text-destructive border-destructive/30 bg-destructive/10";
  return "text-muted-foreground border-border/40 bg-secondary/50";
}

function recomendacaoStyle(rec: string) {
  if (rec === "COMPRAR") return { bg: "bg-accent/10 border-accent/40 text-accent", Icon: TrendingUp };
  if (rec === "EVITAR") return { bg: "bg-destructive/10 border-destructive/40 text-destructive", Icon: TrendingDown };
  return { bg: "bg-secondary border-border/40 text-muted-foreground", Icon: Minus };
}

function ratingColor(r: string) {
  if (r === "A") return "bg-accent text-accent-foreground";
  if (r === "B") return "bg-blue-500 text-white";
  if (r === "C") return "bg-yellow-500 text-black";
  if (r === "D") return "bg-orange-500 text-white";
  return "bg-destructive text-destructive-foreground";
}

function CollapseSection({
  title,
  subtitle,
  children,
  defaultOpen = false,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border border-border/20 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between p-3 bg-secondary/30 hover:bg-secondary/50 transition-colors text-left"
      >
        <div>
          <p className="text-sm font-medium">{title}</p>
          {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
        </div>
        {open ? <ChevronUp className="w-4 h-4 text-muted-foreground shrink-0" /> : <ChevronDown className="w-4 h-4 text-muted-foreground shrink-0" />}
      </button>
      {open && <div className="p-3 space-y-2">{children}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface Props {
  ticker: string;
}

export default function DeepAnalysisPanel({ ticker }: Props) {
  const [result, setResult] = useState<DeepAnalysisResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async () => {
    if (loading) return;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchDeepAnalysis(ticker);
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao conectar com a API.");
    } finally {
      setLoading(false);
    }
  }, [ticker, loading]);

  const decision = result?.final_decision;
  const { bg: recBg, Icon: RecIcon } = decision
    ? recomendacaoStyle(decision.recomendacao)
    : { bg: "", Icon: Minus };

  return (
    <Card className="bg-card border-border/30">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-base font-[family-name:var(--font-display)] flex items-center gap-2">
              <Brain className="w-4 h-4 text-primary" />
              Análise Profunda (Multi-Agente)
            </CardTitle>
            <CardDescription>5 agentes IA: Macro → Fundamentos → Risco → Personas → Decisão</CardDescription>
          </div>
          <Button
            size="sm"
            variant={result ? "outline" : "default"}
            onClick={run}
            disabled={loading}
            className="gap-1.5"
          >
            {loading
              ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
              : <Sparkles className="w-3.5 h-3.5" />}
            {result ? "Reanalisar" : "Analisar"}
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Idle state */}
        {!result && !loading && !error && (
          <p className="text-sm text-muted-foreground">
            Clique em "Analisar" para executar o pipeline de 5 agentes: contexto macro,
            fundamentos + DDM, risco quantitativo, perspectivas Barsi/Crescimento e
            recomendação final auditável.
          </p>
        )}

        {/* Loading */}
        {loading && (
          <div className="space-y-2 py-2">
            {["Macro Agent", "Fundamental Agent", "Risk Agent", "Persona Agent", "Decision Agent"].map((a, i) => (
              <div key={a} className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="w-3.5 h-3.5 animate-spin text-primary" style={{ animationDelay: `${i * 0.15}s` }} />
                {a}
              </div>
            ))}
          </div>
        )}

        {/* Error */}
        {error && (
          <p className="text-sm text-destructive">{error}</p>
        )}

        {/* Results */}
        {result && !loading && (
          <>
            {!result.success && (
              <p className="text-sm text-destructive">{result.error || "Pipeline falhou."}</p>
            )}

            {result.success && decision && (
              <>
                {/* Decision header */}
                <div className={`flex items-center justify-between p-4 rounded-lg border ${recBg}`}>
                  <div className="flex items-center gap-3">
                    <RecIcon className="w-6 h-6" />
                    <div>
                      <p className="font-bold text-lg">{decision.recomendacao}</p>
                      <p className="text-xs opacity-80">Sinal {decision.forca_sinal}</p>
                    </div>
                  </div>
                  <div className="text-right space-y-1">
                    <Badge className={`text-sm font-bold ${ratingColor(decision.rating)}`}>
                      Rating {decision.rating}
                    </Badge>
                    {decision.dy_alvo_minimo && (
                      <p className="text-xs opacity-80">DY mín: {decision.dy_alvo_minimo.toFixed(1)}%</p>
                    )}
                  </div>
                </div>

                {/* Tese */}
                <div className="text-sm leading-relaxed bg-secondary/30 rounded-lg p-3 border border-border/20">
                  {decision.tese}
                </div>

                {/* Price targets */}
                {(decision.preco_entrada_ideal || decision.preco_alvo_12m || decision.stop_sugerido) && (
                  <div className="grid grid-cols-3 gap-2">
                    {decision.preco_entrada_ideal && (
                      <div className="p-2 rounded-lg bg-accent/5 border border-accent/20 text-center">
                        <p className="text-xs text-muted-foreground mb-1">Entrada ideal</p>
                        <p className="text-sm font-bold font-mono text-accent">
                          R$ {decision.preco_entrada_ideal.toFixed(2)}
                        </p>
                      </div>
                    )}
                    {decision.preco_alvo_12m && (
                      <div className="p-2 rounded-lg bg-blue-500/5 border border-blue-500/20 text-center">
                        <p className="text-xs text-muted-foreground mb-1">Alvo 12m</p>
                        <p className="text-sm font-bold font-mono text-blue-400">
                          R$ {decision.preco_alvo_12m.toFixed(2)}
                        </p>
                      </div>
                    )}
                    {decision.stop_sugerido && (
                      <div className="p-2 rounded-lg bg-destructive/5 border border-destructive/20 text-center">
                        <p className="text-xs text-muted-foreground mb-1">Stop</p>
                        <p className="text-sm font-bold font-mono text-destructive">
                          R$ {decision.stop_sugerido.toFixed(2)}
                        </p>
                      </div>
                    )}
                  </div>
                )}

                {/* Collapsible sections */}
                <div className="space-y-2">

                  {/* Macro */}
                  <CollapseSection
                    title="Macro Agent"
                    subtitle={`${result.macro_analysis.ciclo_juros} • spread CDI ${result.macro_analysis.spread_cdi > 0 ? "+" : ""}${result.macro_analysis.spread_cdi?.toFixed(2)}%`}
                  >
                    <p className="text-xs text-muted-foreground">{result.macro_analysis.contexto}</p>
                    <div className="grid grid-cols-2 gap-2 mt-2">
                      <div className="text-xs">
                        <span className="text-muted-foreground">DY real: </span>
                        <span className="font-mono font-medium">{result.macro_analysis.dy_real?.toFixed(2)}%</span>
                      </div>
                      <div className="text-xs">
                        <span className="text-muted-foreground">Yield mín aceitável: </span>
                        <span className="font-mono font-medium">{result.macro_analysis.yield_minimo_aceitavel?.toFixed(1)}%</span>
                      </div>
                    </div>
                    {result.macro_analysis.alerta && (
                      <p className="text-xs text-yellow-400 mt-1">⚠ {result.macro_analysis.alerta}</p>
                    )}
                  </CollapseSection>

                  {/* Fundamentos */}
                  <CollapseSection
                    title="Fundamental Agent"
                    subtitle={`${result.fundamental_analysis.qualidade} • ${result.fundamental_analysis.pvp_status}`}
                  >
                    <p className="text-xs text-muted-foreground">{result.fundamental_analysis.resumo}</p>
                    {(result.fundamental_analysis.ddm_preco_justo || result.fundamental_analysis.ddm_upside_pct != null) && (
                      <div className="flex gap-4 mt-2">
                        {result.fundamental_analysis.ddm_preco_justo && (
                          <div className="text-xs">
                            <span className="text-muted-foreground">DDM preço justo: </span>
                            <span className="font-mono font-bold">R$ {result.fundamental_analysis.ddm_preco_justo.toFixed(2)}</span>
                          </div>
                        )}
                        {result.fundamental_analysis.ddm_upside_pct != null && (
                          <div className="text-xs">
                            <span className="text-muted-foreground">Upside: </span>
                            <span className={`font-mono font-bold ${result.fundamental_analysis.ddm_upside_pct >= 0 ? "text-accent" : "text-destructive"}`}>
                              {result.fundamental_analysis.ddm_upside_pct > 0 ? "+" : ""}{result.fundamental_analysis.ddm_upside_pct.toFixed(1)}%
                            </span>
                          </div>
                        )}
                      </div>
                    )}
                    {result.fundamental_analysis.pontos_fortes.length > 0 && (
                      <ul className="text-xs space-y-0.5 mt-2">
                        {result.fundamental_analysis.pontos_fortes.map((p, i) => (
                          <li key={i} className="text-accent">+ {p}</li>
                        ))}
                        {result.fundamental_analysis.pontos_fracos.map((p, i) => (
                          <li key={i} className="text-destructive">− {p}</li>
                        ))}
                      </ul>
                    )}
                  </CollapseSection>

                  {/* Risco */}
                  <CollapseSection
                    title="Risk Agent"
                    subtitle={`Risco geral: ${result.risk_analysis.nivel_risco}`}
                  >
                    <p className="text-xs text-muted-foreground">{result.risk_analysis.resumo_risco}</p>
                    <div className="grid grid-cols-2 gap-1.5 mt-2">
                      {(["risco_liquidez", "risco_credito", "risco_vacancia", "risco_juros"] as const).map((k) => (
                        <div key={k} className="flex items-center justify-between text-xs">
                          <span className="text-muted-foreground capitalize">{k.replace("risco_", "")}</span>
                          <Badge variant="outline" className={`text-xs py-0 ${riskColor(result.risk_analysis[k])}`}>
                            {result.risk_analysis[k]}
                          </Badge>
                        </div>
                      ))}
                    </div>
                    {result.risk_analysis.cenario_stress && (
                      <div className="mt-2 text-xs">
                        <span className="text-muted-foreground">Stress SELIC+2pp: </span>
                        <span>{result.risk_analysis.cenario_stress}</span>
                      </div>
                    )}
                  </CollapseSection>

                  {/* Personas */}
                  <CollapseSection
                    title="Persona Agent"
                    subtitle={`Barsi: ${result.persona_analysis.barsi?.opiniao} • Crescimento: ${result.persona_analysis.crescimento?.opiniao}`}
                  >
                    <div className="space-y-3">
                      {(["barsi", "crescimento"] as const).map((persona) => {
                        const p = result.persona_analysis[persona];
                        return (
                          <div key={persona} className="space-y-1">
                            <div className="flex items-center gap-2">
                              {persona === "barsi"
                                ? <ShieldCheck className="w-3.5 h-3.5 text-blue-400" />
                                : <Target className="w-3.5 h-3.5 text-purple-400" />}
                              <span className="text-xs font-medium capitalize">
                                {persona === "barsi" ? "Barsi (conservador)" : "Crescimento (agressivo)"}
                              </span>
                              <Badge variant="outline" className={`text-xs py-0 ${opiniaoColor(p.opiniao)}`}>
                                {p.opiniao}
                              </Badge>
                            </div>
                            <p className="text-xs text-muted-foreground pl-5">{p.raciocinio}</p>
                            <p className="text-xs text-muted-foreground/70 pl-5 italic">{p.condicao_entrada}</p>
                          </div>
                        );
                      })}
                    </div>
                  </CollapseSection>

                  {/* Gatilhos */}
                  {(decision.gatilhos_compra.length > 0 || decision.gatilhos_saida.length > 0) && (
                    <CollapseSection title="Gatilhos" subtitle="Condições para compra e saída">
                      {decision.gatilhos_compra.length > 0 && (
                        <div className="space-y-1">
                          <p className="text-xs text-muted-foreground font-medium">Compra:</p>
                          {decision.gatilhos_compra.map((g, i) => (
                            <p key={i} className="text-xs text-accent pl-2">+ {g}</p>
                          ))}
                        </div>
                      )}
                      {decision.gatilhos_saida.length > 0 && (
                        <div className="space-y-1">
                          <p className="text-xs text-muted-foreground font-medium">Saída:</p>
                          {decision.gatilhos_saida.map((g, i) => (
                            <p key={i} className="text-xs text-destructive pl-2">− {g}</p>
                          ))}
                        </div>
                      )}
                    </CollapseSection>
                  )}
                </div>

                {/* Pipeline meta */}
                {result.pipeline_meta && (
                  <div className="text-xs text-muted-foreground/50 flex items-center gap-3">
                    <span>{result.pipeline_meta.agents_run} agentes</span>
                    <span>{result.pipeline_meta.total_s.toFixed(1)}s total</span>
                    {result.pipeline_meta.errors.length > 0 && (
                      <span className="text-yellow-500/70">
                        {result.pipeline_meta.errors.length} fallback(s)
                      </span>
                    )}
                  </div>
                )}
              </>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
