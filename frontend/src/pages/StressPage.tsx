import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Label } from "@/components/ui/label";
import { AlertTriangle, Loader2, Shield, TrendingDown, Download } from "lucide-react";
import { usePortfolio } from "@/hooks/use-portfolio";
import { useStressTest } from "@/hooks/use-api";

export default function StressPage() {
  const { tickers, quantities, isEmpty } = usePortfolio();
  const stressMutation = useStressTest();
  const [results, setResults] = useState<Array<Record<string, unknown>> | null>(null);
  const [customJuros, setCustomJuros] = useState([0]);     // -5 to 5 pp
  const [customInflacao, setCustomInflacao] = useState([0]); // -5 to 5 pp
  const [customVacancia, setCustomVacancia] = useState([0]);   // 0 to 30 pp

  const handleRunStress = () => {
    if (isEmpty) return;
    
    const juros = customJuros[0];
    const inflacao = customInflacao[0];
    const vacancia = customVacancia[0];

    // Basic heuristic to translate macroeconomic changes into % shocks for sectors
    const isTijolo = ["Logística", "Shopping", "Lajes Corp."];
    
    // Paper values benefit from rates and inflation theoretically via indexing
    const p_papel = (juros * 0.01) + (inflacao * 0.015);
    // Real estate struggles with high rates, but rental pass-through counters inflation mildly
    const p_tijolo = (juros * -0.04) + (inflacao * 0.005) + (vacancia * -0.01);
    const p_fundofundos = (p_papel + p_tijolo) / 2;
    
    const d_papel = (juros * 0.015) + (inflacao * 0.02);
    const d_tijolo = (vacancia * -0.015); // Vacancy hits dividend yields directly
    const d_fundofundos = (d_papel + d_tijolo) / 2;

    const price_shock: Record<string, number> = {
       "Papel (CRI)": p_papel,
       "Fundo de Fundos": p_fundofundos,
       "Outros": p_fundofundos
    };
    const dividend_shock: Record<string, number> = {
       "Papel (CRI)": d_papel,
       "Fundo de Fundos": d_fundofundos,
       "Outros": d_fundofundos
    };

    isTijolo.forEach(t => {
       price_shock[t] = p_tijolo;
       dividend_shock[t] = d_tijolo;
    });

    const custom_scenario = {
        name: "Cenário Personalizado (Geral)",
        price_shock,
        dividend_shock
    };

    stressMutation.mutate(
      { tickers, quantities, custom_scenario },
      {
        onSuccess: (data) => setResults(data.scenarios),
      }
    );
  };

  const handleExportCSV = () => {
    if (!results || results.length === 0) return;
    const headers = ["Cenário", "Patrimônio Antes", "Patrimônio Depois", "Impacto Patrimônio (%)", "Dividendo Antes", "Dividendo Depois", "Impacto Dividendo (%)"];
    const rows = results.map((scenario: any) => {
      const name = String(scenario.cenario || scenario.scenario || scenario.scenario_name || "Cenário");
      const pa = Number(scenario.patrimonio_antes || scenario.total_antes || 0);
      const pd = Number(scenario.patrimonio_apos || scenario.total_depois || 0);
      const imp = pa > 0 ? ((pd - pa) / pa) * 100 : 0;
      const da = Number(scenario.dividendo_mensal_antes || scenario.dividendos_antes || 0);
      const dd = Number(scenario.dividendo_mensal_apos || scenario.dividendos_depois || 0);
      const id = da > 0 ? ((dd - da) / da) * 100 : 0;
      
      return [
        `"${name}"`, pa.toFixed(2), pd.toFixed(2), imp.toFixed(2), da.toFixed(2), dd.toFixed(2), id.toFixed(2)
      ].join(",");
    });
    
    const csvContent = "data:text/csv;charset=utf-8,\uFEFF" + [headers.join(","), ...rows].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", "stress_test_alphacota.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
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
          <div className="grid grid-cols-1 md:grid-cols-[1fr_300px] gap-6">
            <Card className="bg-card border-border/30 shadow-none">
              <CardHeader className="pb-3 border-b border-border/10 cursor-pointer">
                <CardTitle className="text-base font-semibold">Cenário Customizado</CardTitle>
                <CardDescription className="text-xs">O impacto estimado de variáveis macroeconômicas</CardDescription>
              </CardHeader>
              <CardContent className="pt-5 space-y-6">
                <div className="space-y-3">
                   <div className="flex justify-between items-center">
                      <Label className="text-xs font-semibold text-muted-foreground">Variação Selic</Label>
                      <Badge variant="outline" className={`font-mono text-xs ${customJuros[0] > 0 ? 'text-destructive' : customJuros[0] < 0 ? 'text-primary' : ''}`}>
                        {customJuros[0] > 0 ? '+' : ''}{customJuros[0]} pp
                      </Badge>
                   </div>
                   <Slider value={customJuros} min={-5} max={5} step={0.25} onValueChange={setCustomJuros} className="py-1" />
                </div>
                
                <div className="space-y-3">
                   <div className="flex justify-between items-center">
                      <Label className="text-xs font-semibold text-muted-foreground">Variação Inflação (IPCA)</Label>
                      <Badge variant="outline" className={`font-mono text-xs ${customInflacao[0] > 0 ? 'text-destructive' : customInflacao[0] < 0 ? 'text-primary' : ''}`}>
                         {customInflacao[0] > 0 ? '+' : ''}{customInflacao[0]} pp
                      </Badge>
                   </div>
                   <Slider value={customInflacao} min={-5} max={5} step={0.25} onValueChange={setCustomInflacao} className="py-1" />
                </div>
                
                <div className="space-y-3">
                   <div className="flex justify-between items-center">
                      <Label className="text-xs font-semibold text-muted-foreground">Aumento Vacância Tijolo</Label>
                      <Badge variant="outline" className={`font-mono text-xs ${customVacancia[0] > 0 ? 'text-destructive' : ''}`}>
                         +{customVacancia[0]} pp
                      </Badge>
                   </div>
                   <Slider value={customVacancia} min={0} max={30} step={1} onValueChange={setCustomVacancia} className="py-1" />
                </div>
              </CardContent>
            </Card>

            <Card className="bg-card border-border/30 flex flex-col justify-center h-full">
              <CardContent className="p-6 text-center space-y-4">
                <div>
                  <h3 className="text-sm font-semibold mb-1">Rodar Simulações</h3>
                  <p className="text-xs text-muted-foreground">Serão processados os cenários padrão junto com seu cenário customizado.</p>
                </div>
                <div className="p-3 bg-muted/30 rounded-lg">
                  <p className="font-semibold text-sm">{tickers.length} FIIs na carteira</p>
                  <p className="text-xs text-muted-foreground line-clamp-2 mt-1 px-2" title={tickers.join(", ")}>
                    {tickers.join(", ")}
                  </p>
                </div>
                <Button size="lg" className="w-full mt-4" onClick={handleRunStress} disabled={stressMutation.isPending}>
                  {stressMutation.isPending ? (
                    <><Loader2 className="w-5 h-5 mr-2 animate-spin" /> Adquirindo Telemetria...</>
                  ) : (
                    <><Shield className="w-5 h-5 mr-2" /> Executar Análise</>
                  )}
                </Button>
              </CardContent>
            </Card>
          </div>

          {stressMutation.isError && (
            <Card className="bg-destructive/10 border-destructive/30">
              <CardContent className="p-4 text-destructive text-sm">
                Erro: {(stressMutation.error as Error).message}
              </CardContent>
            </Card>
          )}

          {results && results.length > 0 && (
            <div className="space-y-4">
              <div className="flex justify-end">
                <Button variant="outline" size="sm" onClick={handleExportCSV}>
                  <Download className="w-4 h-4 mr-2" />
                  Exportar CSV
                </Button>
              </div>
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
            </div>
          )}
        </>
      )}
    </div>
  );
}
