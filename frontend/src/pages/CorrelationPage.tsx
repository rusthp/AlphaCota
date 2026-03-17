import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { GitBranch, Loader2, AlertTriangle } from "lucide-react";
import { usePortfolio } from "@/hooks/use-portfolio";
import { useCorrelation } from "@/hooks/use-api";

export default function CorrelationPage() {
  const { tickers, isEmpty } = usePortfolio();
  const correlationMutation = useCorrelation();
  const [results, setResults] = useState<{
    tickers: string[];
    matrix: Record<string, Record<string, number>>;
  } | null>(null);

  const handleRun = () => {
    if (isEmpty || tickers.length < 2) return;
    correlationMutation.mutate(
      { tickers },
      { onSuccess: (data) => setResults(data) }
    );
  };

  const getColor = (val: number): string => {
    if (val >= 0.8) return "bg-red-500/80 text-white";
    if (val >= 0.5) return "bg-orange-500/60 text-white";
    if (val >= 0.2) return "bg-yellow-500/40 text-foreground";
    if (val >= -0.2) return "bg-muted text-muted-foreground";
    if (val >= -0.5) return "bg-blue-500/40 text-foreground";
    return "bg-blue-600/70 text-white";
  };

  const getLabel = (val: number): string => {
    if (val >= 0.8) return "Forte +";
    if (val >= 0.5) return "Moderada +";
    if (val >= 0.2) return "Fraca +";
    if (val >= -0.2) return "Neutra";
    if (val >= -0.5) return "Fraca −";
    return "Forte −";
  };

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-3">
          <GitBranch className="w-6 h-6 text-primary" />
          Matriz de Correlação
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Analise a correlação entre os FIIs da sua carteira
        </p>
      </div>

      {isEmpty || tickers.length < 2 ? (
        <Card className="bg-card border-border/30">
          <CardContent className="p-12 text-center">
            <AlertTriangle className="w-12 h-12 text-muted-foreground/30 mx-auto mb-4" />
            <h3 className="text-lg font-semibold mb-2">Mínimo 2 FIIs</h3>
            <p className="text-sm text-muted-foreground">
              Adicione ao menos 2 FIIs em "Minha Carteira" para ver a correlação.
            </p>
          </CardContent>
        </Card>
      ) : (
        <>
          <Card className="bg-card border-border/30">
            <CardContent className="p-4 flex items-center justify-between">
              <div>
                <p className="font-semibold">{tickers.length} FIIs na carteira</p>
                <p className="text-xs text-muted-foreground">{tickers.join(", ")}</p>
              </div>
              <Button onClick={handleRun} disabled={correlationMutation.isPending}>
                {correlationMutation.isPending ? (
                  <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Calculando...</>
                ) : (
                  <><GitBranch className="w-4 h-4 mr-2" /> Calcular Correlação</>
                )}
              </Button>
            </CardContent>
          </Card>

          {correlationMutation.isError && (
            <Card className="bg-destructive/10 border-destructive/30">
              <CardContent className="p-4 text-destructive text-sm">
                Erro: {(correlationMutation.error as Error).message}
              </CardContent>
            </Card>
          )}

          {results && (
            <Card className="bg-card border-border/30">
              <CardHeader>
                <CardTitle className="text-sm">Heatmap de Correlação</CardTitle>
              </CardHeader>
              <CardContent>
                {/* Legend */}
                <div className="flex gap-2 mb-4 flex-wrap">
                  {[
                    { label: "Forte +", color: "bg-red-500/80" },
                    { label: "Moderada +", color: "bg-orange-500/60" },
                    { label: "Fraca +", color: "bg-yellow-500/40" },
                    { label: "Neutra", color: "bg-muted" },
                    { label: "Fraca −", color: "bg-blue-500/40" },
                    { label: "Forte −", color: "bg-blue-600/70" },
                  ].map((item) => (
                    <div key={item.label} className="flex items-center gap-1">
                      <div className={`w-3 h-3 rounded ${item.color}`} />
                      <span className="text-[10px] text-muted-foreground">{item.label}</span>
                    </div>
                  ))}
                </div>

                {/* Heatmap table */}
                <div className="overflow-x-auto">
                  <table className="w-full text-xs font-mono">
                    <thead>
                      <tr>
                        <th className="p-2 text-left text-muted-foreground"></th>
                        {results.tickers.map((t) => (
                          <th key={t} className="p-2 text-center text-muted-foreground font-medium">
                            {t}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {results.tickers.map((rowTicker) => (
                        <tr key={rowTicker}>
                          <td className="p-2 font-medium text-muted-foreground">{rowTicker}</td>
                          {results.tickers.map((colTicker) => {
                            const val = results.matrix[rowTicker]?.[colTicker] ?? 0;
                            const isDiagonal = rowTicker === colTicker;
                            return (
                              <td
                                key={colTicker}
                                className={`p-2 text-center rounded-sm ${
                                  isDiagonal ? "bg-primary/20 text-primary font-bold" : getColor(val)
                                }`}
                                title={`${rowTicker} × ${colTicker}: ${val.toFixed(3)} (${getLabel(val)})`}
                              >
                                {isDiagonal ? "1.00" : val.toFixed(2)}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Insights */}
                <div className="mt-6 space-y-2">
                  <h4 className="text-xs font-semibold text-muted-foreground">Insights</h4>
                  {(() => {
                    const pairs: { a: string; b: string; val: number }[] = [];
                    for (let i = 0; i < results.tickers.length; i++) {
                      for (let j = i + 1; j < results.tickers.length; j++) {
                        const a = results.tickers[i];
                        const b = results.tickers[j];
                        const val = results.matrix[a]?.[b] ?? 0;
                        pairs.push({ a, b, val });
                      }
                    }
                    const sorted = [...pairs].sort((x, y) => Math.abs(y.val) - Math.abs(x.val));
                    const highest = sorted[0];
                    const lowest = sorted[sorted.length - 1];

                    return (
                      <div className="flex flex-wrap gap-2">
                        {highest && (
                          <Badge variant="outline" className="text-xs">
                            Maior correlação: {highest.a}×{highest.b} = {highest.val.toFixed(2)}
                          </Badge>
                        )}
                        {lowest && (
                          <Badge variant="outline" className="text-xs">
                            Menor correlação: {lowest.a}×{lowest.b} = {lowest.val.toFixed(2)}
                          </Badge>
                        )}
                        <Badge variant="outline" className="text-xs border-primary/30 text-primary">
                          {pairs.filter((p) => p.val < 0.3).length} pares com boa diversificação
                        </Badge>
                      </div>
                    );
                  })()}
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
