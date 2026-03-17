import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AlertTriangle, Loader2, Shield, TrendingDown } from "lucide-react";
import { usePortfolio } from "@/hooks/use-portfolio";
import { useStressTest } from "@/hooks/use-api";

export default function StressPage() {
  const { tickers, quantities, isEmpty } = usePortfolio();
  const stressMutation = useStressTest();
  const [results, setResults] = useState<Array<Record<string, unknown>> | null>(null);

  const handleRunStress = () => {
    if (isEmpty) return;
    stressMutation.mutate(
      { tickers, quantities },
      {
        onSuccess: (data) => setResults(data.scenarios),
      }
    );
  };

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-3">
          <Shield className="w-6 h-6 text-primary" />
          Stress Test
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Simule cenários adversos na sua carteira de FIIs
        </p>
      </div>

      {isEmpty ? (
        <Card className="bg-card border-border/30">
          <CardContent className="p-12 text-center">
            <AlertTriangle className="w-12 h-12 text-muted-foreground/30 mx-auto mb-4" />
            <h3 className="text-lg font-semibold mb-2">Carteira vazia</h3>
            <p className="text-sm text-muted-foreground">
              Adicione FIIs em "Minha Carteira" para rodar o stress test.
            </p>
          </CardContent>
        </Card>
      ) : (
        <>
          <Card className="bg-card border-border/30">
            <CardContent className="p-4 flex items-center justify-between">
              <div>
                <p className="font-semibold">{tickers.length} FIIs na carteira</p>
                <p className="text-xs text-muted-foreground">
                  {tickers.join(", ")}
                </p>
              </div>
              <Button onClick={handleRunStress} disabled={stressMutation.isPending}>
                {stressMutation.isPending ? (
                  <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Simulando...</>
                ) : (
                  <><AlertTriangle className="w-4 h-4 mr-2" /> Rodar Stress Test</>
                )}
              </Button>
            </CardContent>
          </Card>

          {stressMutation.isError && (
            <Card className="bg-destructive/10 border-destructive/30">
              <CardContent className="p-4 text-destructive text-sm">
                Erro: {(stressMutation.error as Error).message}
              </CardContent>
            </Card>
          )}

          {results && results.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {results.map((scenario, i) => {
                const name = String(scenario.cenario || scenario.scenario || `Cenário ${i + 1}`);
                const patrimonioAntes = Number(scenario.patrimonio_antes || 0);
                const patrimonioDepois = Number(scenario.patrimonio_apos || 0);
                const impacto = patrimonioAntes > 0 ? ((patrimonioDepois - patrimonioAntes) / patrimonioAntes) * 100 : 0;
                const dividendoAntes = Number(scenario.dividendo_mensal_antes || 0);
                const dividendoDepois = Number(scenario.dividendo_mensal_apos || 0);
                const divImpacto = dividendoAntes > 0 ? ((dividendoDepois - dividendoAntes) / dividendoAntes) * 100 : 0;

                return (
                  <Card key={i} className="bg-card border-border/30">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm flex items-center gap-2">
                        <TrendingDown className="w-4 h-4 text-destructive" />
                        {name}
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      <div className="flex justify-between text-sm">
                        <span className="text-muted-foreground">Patrimônio</span>
                        <span className="font-mono">
                          R$ {patrimonioAntes.toLocaleString("pt-BR", { minimumFractionDigits: 0 })}
                          <span className="text-destructive font-bold ml-2">
                            {impacto.toFixed(1)}%
                          </span>
                          {" "}→ R$ {patrimonioDepois.toLocaleString("pt-BR", { minimumFractionDigits: 0 })}
                        </span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-muted-foreground">Dividendos/mês</span>
                        <span className="font-mono">
                          R$ {dividendoAntes.toFixed(2)}
                          <span className="text-destructive font-bold ml-2">
                            {divImpacto.toFixed(1)}%
                          </span>
                          {" "}→ R$ {dividendoDepois.toFixed(2)}
                        </span>
                      </div>
                      <Badge variant="outline" className={`text-xs ${impacto > -10 ? "border-yellow-500/30 text-yellow-500" : "border-destructive/30 text-destructive"}`}>
                        {impacto > -10 ? "Impacto Moderado" : impacto > -25 ? "Impacto Alto" : "Impacto Severo"}
                      </Badge>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
}
