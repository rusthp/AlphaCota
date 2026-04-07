import { useState, useMemo, useEffect } from "react";
import {
  Brain, Calendar, Info, LineChart as LineChartIcon, Percent, RefreshCw, Target, TrendingUp, DollarSign, Wallet, Activity
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { usePortfolio } from "@/hooks/use-portfolio";
import { useScanner, useMonteCarlo } from "@/hooks/use-api";

// ─── Types ────────────────────────────────────────────────────────────────────

type SimMode = "accumulation" | "fire";
type Scenario = "conservador" | "moderado" | "agressivo";

const SCENARIOS: Record<Scenario, { label: string; dy: number; inflation: number; color: string }> = {
  conservador: { label: "Conservador",  dy: 7.0,  inflation: 4.5, color: "text-blue-400" },
  moderado:    { label: "Moderado",     dy: 9.5,  inflation: 4.5, color: "text-accent" },
  agressivo:   { label: "Agressivo",    dy: 12.0, inflation: 4.5, color: "text-red-400" },
};

// ─── Formatters ───────────────────────────────────────────────────────────────

function fmtCurrency(v: number) {
  if (v >= 1_000_000) return `R$ ${(v / 1_000_000).toFixed(2)}M`;
  if (v >= 1_000)     return `R$ ${(v / 1_000).toFixed(0)}k`;
  return `R$ ${v.toFixed(0)}`;
}

function fmtFull(v: number) {
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

// ─── Simulation logic ─────────────────────────────────────────────────────────

function runSimulation(params: {
  initialCapital: number;
  monthlyInvestment: number;
  avgDY: number;
  inflation: number;
  years: number;
  reinvest: boolean;
}) {
  const { initialCapital, monthlyInvestment, avgDY, inflation, years, reinvest } = params;
  const monthlyDY = avgDY / 100 / 12;
  const monthlyInflation = inflation / 100 / 12;

  const data: {
    month: number;
    year: string;
    patrimony: number;
    patrimonyReal: number;
    income: number;
    incomeReal: number;
    invested: number;
  }[] = [];

  let patrimony = initialCapital;
  let totalInvested = initialCapital;
  let inflationFactor = 1;

  for (let m = 0; m <= years * 12; m++) {
    const monthlyIncome = patrimony * monthlyDY;
    inflationFactor *= (1 + monthlyInflation);

    if (m % 6 === 0) {
      data.push({
        month: m,
        year: `Ano ${Math.floor(m / 12)}`,
        patrimony: Math.round(patrimony),
        patrimonyReal: Math.round(patrimony / inflationFactor),
        income: Math.round(monthlyIncome),
        incomeReal: Math.round(monthlyIncome / inflationFactor),
        invested: Math.round(totalInvested),
      });
    }

    if (reinvest) patrimony += monthlyIncome;
    patrimony += monthlyInvestment;
    totalInvested += monthlyInvestment;
  }
  return data;
}

// ─── FIRE reverse calculator ──────────────────────────────────────────────────

function calcFireReverse(params: {
  targetMonthlyIncome: number;
  monthlyInvestment: number;
  avgDY: number;
  inflation: number;
  initialCapital: number;
}) {
  const { targetMonthlyIncome, monthlyInvestment, avgDY, inflation, initialCapital } = params;
  const monthlyDY = avgDY / 100 / 12;
  const requiredCapital = targetMonthlyIncome / monthlyDY;

  // How many months to reach requiredCapital via reinvestment + monthly contributions
  let patrimony = initialCapital;
  let months = 0;
  const MAX_MONTHS = 600; // 50 years cap
  while (patrimony < requiredCapital && months < MAX_MONTHS) {
    patrimony += patrimony * monthlyDY + monthlyInvestment;
    months++;
  }

  const yearsToFire = months / 12;
  // Inflation-adjusted target (in today's money)
  const inflationFactor = Math.pow(1 + inflation / 100, yearsToFire);
  const targetInflated = targetMonthlyIncome * inflationFactor;

  return { requiredCapital, months, yearsToFire, targetInflated };
}

// ─── Component ────────────────────────────────────────────────────────────────

const SimulatorPage = () => {
  const { portfolio, isEmpty: portfolioEmpty } = usePortfolio();
  const { data: scannerData } = useScanner();

  // Portfolio stats
  const portfolioStats = useMemo(() => {
    if (portfolioEmpty || !scannerData) return null;
    const priceMap: Record<string, number> = {};
    const dyMap: Record<string, number> = {};
    scannerData.fiis.forEach((f) => { priceMap[f.ticker] = f.price; dyMap[f.ticker] = f.dy; });
    let totalValue = 0; let weightedDY = 0;
    for (const a of portfolio.assets) {
      const price = priceMap[a.ticker] || a.avgPrice;
      const value = a.quantity * price;
      const dy = dyMap[a.ticker] || 9;
      totalValue += value; weightedDY += value * dy;
    }
    return { totalValue: Math.round(totalValue), avgDY: totalValue > 0 ? weightedDY / totalValue : 9 };
  }, [portfolio.assets, scannerData, portfolioEmpty]);

  // Mode
  const [mode, setMode] = useState<SimMode>("accumulation");
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [useMC, setUseMC] = useState(false);
  const mcMutation = useMonteCarlo();

  // Parameters
  const [initialCapital, setInitialCapital] = useState(10_000);
  const [monthlyInvestment, setMonthlyInvestment] = useState(1_000);
  const [avgDY, setAvgDY] = useState(9);
  const [inflation, setInflation] = useState(4.5);
  const [years, setYears] = useState(20);
  const [reinvest, setReinvest] = useState(true);

  // FIRE reverse mode
  const [targetIncome, setTargetIncome] = useState(5_000);

  // Sync portfolio stats on load
  useEffect(() => {
    if (portfolioStats) {
      setInitialCapital(portfolioStats.totalValue);
      setAvgDY(Math.round(portfolioStats.avgDY * 10) / 10);
    }
  }, [portfolioStats]);

  // Apply scenario preset
  const applyScenario = (sc: Scenario) => {
    setScenario(sc);
    setAvgDY(SCENARIOS[sc].dy);
    setInflation(SCENARIOS[sc].inflation);
  };

  // Simulation
  const simulation = useMemo(() => runSimulation({
    initialCapital, monthlyInvestment, avgDY, inflation, years, reinvest,
  }), [initialCapital, monthlyInvestment, avgDY, inflation, years, reinvest]);

  const finalData = simulation[simulation.length - 1];
  const totalDividends = finalData.patrimony - finalData.invested;

  // FIRE reverse
  const fireReverse = useMemo(() => calcFireReverse({
    targetMonthlyIncome: targetIncome,
    monthlyInvestment,
    avgDY,
    inflation,
    initialCapital,
  }), [targetIncome, monthlyInvestment, avgDY, inflation, initialCapital]);

  // Monte Carlo execution
  useEffect(() => {
    if (!useMC) return;
    
    // Simulate real delay to avoid immediate spamming while dragging slider
    const t = setTimeout(() => {
      let tickers = portfolio.assets.map(a => a.ticker);
      if (tickers.length === 0) tickers = ["MXRF11", "HGLG11"]; // generic fallback
      
      const vols: Record<string, number> = {};
      const growths: Record<string, number> = {};
      
      const assumedAnnualGrowth = (avgDY / 100); 
      
      tickers.forEach(t => {
         if (scannerData) {
            const match = scannerData.fiis.find(f => f.ticker === t);
            vols[t] = match ? Math.max((match as any).volatilidade_30d || 0.05, 0.02) : 0.05;
         } else {
            vols[t] = 0.05;
         }
         growths[t] = assumedAnnualGrowth;
      });

      mcMutation.mutate({
        tickers,
        aporte_mensal: monthlyInvestment,
        meses: years * 12,
        simulacoes: 300, // run fast
        override_initial_capital: initialCapital,
        growth_rates: growths,
        volatilities: vols
      });
    }, 800);

    return () => clearTimeout(t);
  }, [useMC, initialCapital, monthlyInvestment, avgDY, years, portfolio.assets, scannerData]);

  const actData = useMC && mcMutation.data?.trajectory ? mcMutation.data.trajectory : simulation;

  const mData = mcMutation.data as any;
  const finalAct = useMC && mData ? {
    patrimony: mData.mediana_valor_final,
    patrimonyReal: mData.mediana_valor_final / Math.pow(1 + inflation / 100, years),
    income: mData.mediana_valor_final * (avgDY / 100 / 12),
    incomeReal: (mData.mediana_valor_final / Math.pow(1 + inflation / 100, years)) * (avgDY / 100 / 12),
    invested: initialCapital + (monthlyInvestment * years * 12)
  } : {
    patrimony: finalData.patrimony,
    patrimonyReal: finalData.patrimonyReal,
    income: finalData.income,
    incomeReal: finalData.incomeReal,
    invested: finalData.invested
  };
  
  const actDividends = finalAct.patrimony - finalAct.invested;

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-3">
            <LineChartIcon className="w-6 h-6 text-primary" />
            Simulador de Renda Passiva
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Projete o crescimento da sua renda com FIIs ao longo do tempo (isentos de IRPF)
          </p>
          {portfolioStats && (
            <Badge variant="outline" className="mt-2 text-xs border-primary/30 text-primary">
              <Wallet className="w-3 h-3 mr-1" />
              Carteira: {fmtCurrency(portfolioStats.totalValue)} | DY {portfolioStats.avgDY.toFixed(1)}%
            </Badge>
          )}
        </div>

        {/* Mode toggle */}
        <div className="flex rounded-lg border border-border/50 overflow-hidden text-sm">
          <button
            onClick={() => setMode("accumulation")}
            className={`px-4 py-1.5 transition-colors ${mode === "accumulation" ? "bg-primary text-primary-foreground" : "hover:bg-secondary text-muted-foreground"}`}
          >
            Acumulação
          </button>
          <button
            onClick={() => setMode("fire")}
            className={`px-4 py-1.5 transition-colors flex items-center gap-1.5 ${mode === "fire" ? "bg-primary text-primary-foreground" : "hover:bg-secondary text-muted-foreground"}`}
          >
            <Target className="w-3.5 h-3.5" /> FIRE
          </button>
        </div>
      </div>

      {/* Scenario presets and MC */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-muted-foreground font-mono">Cenário:</span>
          {(Object.entries(SCENARIOS) as [Scenario, typeof SCENARIOS[Scenario]][]).map(([key, sc]) => (
            <button
              key={key}
              onClick={() => applyScenario(key)}
              className={`px-3 py-1 rounded-lg text-xs font-mono border transition-colors ${
                scenario === key
                  ? "bg-primary/20 border-primary/50 text-primary"
                  : "bg-secondary border-border/50 text-muted-foreground hover:text-foreground"
              }`}
            >
              {sc.label} ({sc.dy}% DY)
            </button>
          ))}
          {scenario && (
            <button
              onClick={() => setScenario(null)}
              className="px-2 py-1 rounded-lg text-xs font-mono text-muted-foreground hover:text-foreground border border-border/50"
            >
              <RefreshCw className="w-3 h-3" />
            </button>
          )}
        </div>
        
        <div className="flex items-center gap-3 bg-secondary/30 px-3 py-1.5 rounded-lg border border-border/50 border-dashed">
          <Activity className={`w-4 h-4 ${useMC ? "text-primary" : "text-muted-foreground"}`} />
          <span className="text-xs font-mono">Motor Monte Carlo (Estocástico)</span>
          <Switch checked={useMC} onCheckedChange={setUseMC} />
        </div>
      </div>

      {/* FIRE Reverse Mode */}
      {mode === "fire" && (
        <div className="glass-card p-6 space-y-5 border-primary/20">
          <h3 className="font-semibold text-sm flex items-center gap-2">
            <Target className="w-4 h-4 text-primary" />
            Modo FIRE — Quanto preciso investir?
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            <div className="space-y-2">
              <label className="text-xs text-muted-foreground font-mono flex justify-between">
                Renda passiva desejada/mês
                <span className="text-foreground">{fmtCurrency(targetIncome)}</span>
              </label>
              <Slider
                value={[targetIncome]}
                onValueChange={([v]) => setTargetIncome(v)}
                min={500} max={50_000} step={500}
                className="py-2"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-lg bg-primary/5 border border-primary/20 p-3 text-center">
                <div className="text-xs text-muted-foreground mb-1">Capital necessário</div>
                <div className="text-lg font-bold font-mono text-primary">
                  {fmtCurrency(fireReverse.requiredCapital)}
                </div>
              </div>
              <div className="rounded-lg bg-accent/5 border border-accent/20 p-3 text-center">
                <div className="text-xs text-muted-foreground mb-1">Tempo até FIRE</div>
                <div className="text-lg font-bold font-mono text-accent">
                  {fireReverse.months >= 600
                    ? "> 50 anos"
                    : `${fireReverse.yearsToFire.toFixed(1)} anos`}
                </div>
              </div>
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            Com DY de <strong>{avgDY}%</strong> a.a. e aporte de <strong>{fmtCurrency(monthlyInvestment)}/mês</strong>,
            você precisa de <strong>{fmtCurrency(fireReverse.requiredCapital)}</strong> para gerar{" "}
            <strong>{fmtCurrency(targetIncome)}/mês</strong> em dividendos.
            Considerando inflação de {inflation}%, o equivalente em moeda futura será{" "}
            <strong>{fmtCurrency(fireReverse.targetInflated)}/mês</strong>.<br/>
            <span className="text-accent mt-1 inline-block">* Simulação considera rendimentos 100% isentos de Imposto de Renda (IRPF) em FIIs, conforme legislação vigente.</span>
          </p>
        </div>
      )}

      {/* Controls */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="glass-card p-6 space-y-5">
          <h3 className="font-semibold text-sm flex items-center gap-2">
            <DollarSign className="w-4 h-4 text-primary" /> Parâmetros
          </h3>

          <div className="space-y-4">
            <div>
              <label className="text-xs text-muted-foreground font-mono mb-2 flex justify-between">
                Capital Inicial <span className="text-foreground">{fmtCurrency(initialCapital)}</span>
              </label>
              <Slider value={[initialCapital]} onValueChange={([v]) => setInitialCapital(v)}
                min={0} max={500_000} step={5_000} className="py-2" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground font-mono mb-2 flex justify-between">
                Aporte Mensal <span className="text-foreground">{fmtCurrency(monthlyInvestment)}</span>
              </label>
              <Slider value={[monthlyInvestment]} onValueChange={([v]) => setMonthlyInvestment(v)}
                min={0} max={20_000} step={100} className="py-2" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground font-mono mb-2 flex justify-between">
                Dividend Yield Médio <span className="text-foreground">{avgDY}% a.a.</span>
              </label>
              <Slider value={[avgDY]} onValueChange={([v]) => { setAvgDY(v); setScenario(null); }}
                min={4} max={18} step={0.5} className="py-2" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground font-mono mb-2 flex justify-between">
                Inflação (IPCA) <span className="text-foreground">{inflation}% a.a.</span>
              </label>
              <Slider value={[inflation]} onValueChange={([v]) => setInflation(v)}
                min={0} max={15} step={0.5} className="py-2" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground font-mono mb-2 flex justify-between">
                Período <span className="text-foreground">{years} anos</span>
              </label>
              <Slider value={[years]} onValueChange={([v]) => setYears(v)}
                min={1} max={40} step={1} className="py-2" />
            </div>
            <div className="flex items-center justify-between pt-2">
              <span className="text-xs text-muted-foreground font-mono">Reinvestir dividendos</span>
              <Button size="sm" variant={reinvest ? "default" : "outline"}
                onClick={() => setReinvest(!reinvest)} className="text-xs h-7">
                {reinvest ? "Sim ✓" : "Não"}
              </Button>
            </div>
          </div>
        </div>

        {/* Results */}
        <div className="grid grid-cols-2 gap-4 content-start">
          {[
            { label: useMC ? "Patrimônio P50" : "Patrimônio Final",       value: fmtCurrency(finalAct.patrimony),     icon: TrendingUp, highlight: true },
            { label: useMC ? "P50 Real" : "Patrimônio (real)",       value: fmtCurrency(finalAct.patrimonyReal), icon: Percent },
            { label: useMC ? "Renda P50" : "Renda Mensal Final",      value: fmtCurrency(finalAct.income),        icon: Calendar, highlight: true },
            { label: "Renda Real (poder comp.)",value: fmtCurrency(finalAct.incomeReal),    icon: DollarSign },
            { label: "Total Investido",         value: fmtCurrency(finalAct.invested),      icon: DollarSign },
            { label: "Ganho com Dividendos",    value: fmtCurrency(actDividends),          icon: Percent },
          ].map((card) => (
            <div key={card.label} className={`glass-card p-4 ${card.highlight ? "glow-primary border-primary/20" : ""}`}>
              <div className="flex items-center gap-1.5 text-muted-foreground text-xs mb-2">
                <card.icon className="w-3.5 h-3.5 text-primary" />
                {card.label}
              </div>
              <div className="text-lg font-bold font-mono">{card.value}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Chart */}
      <div className="glass-card p-6 relative">
        <h3 className="font-semibold text-sm mb-4">Projeção de Crescimento Patrimonial {useMC && "(P10 - P90)"}</h3>
        {useMC && mcMutation.isPending && (
           <div className="absolute inset-x-0 top-1/2 flex items-center justify-center z-10 w-full">
              <Badge variant="outline" className="bg-background shadow-lg text-primary border-primary/40 text-xs px-3 py-1">
                 <RefreshCw className="w-3 h-3 mr-2 animate-spin" /> Calculando 300 cenários...
              </Badge>
           </div>
        )}
        <div className={`h-80 transition-opacity duration-300 ${useMC && mcMutation.isPending ? "opacity-30" : "opacity-100"}`}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={actData}>
              <defs>
                <linearGradient id="gradPatrimony" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="hsl(173, 80%, 50%)" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="hsl(173, 80%, 50%)" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gradReal" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="hsl(215, 80%, 60%)" stopOpacity={0.2} />
                  <stop offset="100%" stopColor="hsl(215, 80%, 60%)" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gradInvested" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="hsl(215, 20%, 55%)" stopOpacity={0.2} />
                  <stop offset="100%" stopColor="hsl(215, 20%, 55%)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(222, 30%, 16%)" />
              <XAxis dataKey="year" tick={{ fontSize: 11, fill: "hsl(215, 20%, 55%)" }}
                tickLine={false} axisLine={false}
                interval={Math.max(1, Math.floor(actData.length / 8))} />
              <YAxis tick={{ fontSize: 11, fill: "hsl(215, 20%, 55%)" }} tickLine={false} axisLine={false}
                tickFormatter={(v) => v >= 1_000_000 ? `${(v / 1_000_000).toFixed(1)}M` : `${(v / 1_000).toFixed(0)}k`} />
              <Tooltip
                contentStyle={{
                  backgroundColor: "hsl(222, 44%, 9%)",
                  border: "1px solid hsl(222, 30%, 16%)",
                  borderRadius: "0.75rem",
                  fontFamily: "JetBrains Mono",
                  fontSize: 12,
                }}
                formatter={(value: number, name: string) => [
                  fmtFull(value),
                  name === "patrimony" ? "Patrimônio nominal" :
                  name === "patrimonyReal" ? "Patrimônio real" :
                  name === "invested" ? "Total investido" : 
                  name === "p50" ? "Mediana P50" :
                  name === "p10" ? "Pessimista P10" :
                  name === "p90" ? "Otimista P90" : 
                  typeof name === 'object' ? "Range Confiança" : name,
                ]}
                labelStyle={{ color: "hsl(215, 20%, 55%)" }}
              />
              <Area type="monotone" dataKey="invested" stroke="hsl(215, 20%, 55%)" fill="url(#gradInvested)" strokeWidth={1.5} />
              
              {!useMC && (
                <>
                  <Area type="monotone" dataKey="patrimonyReal" stroke="hsl(215, 80%, 60%)" fill="url(#gradReal)" strokeWidth={1.5} strokeDasharray="4 2" />
                  <Area type="monotone" dataKey="patrimony" stroke="hsl(173, 80%, 50%)" fill="url(#gradPatrimony)" strokeWidth={2} />
                </>
              )}
              
              {useMC && (
                <>
                  {/* Range from p10 to p90 represented by single area where top is p90 and bottom is p10 */}
                  <Area type="monotone" dataKey={["p10", "p90"] as any} stroke="none" fill="hsl(173, 80%, 50%)" fillOpacity={0.15} />
                  <Area type="monotone" dataKey="p50" stroke="hsl(173, 80%, 50%)" fill="none" strokeWidth={2} />
                  <Area type="monotone" dataKey="p10" stroke="hsl(173, 80%, 50%)" strokeOpacity={0.4} strokeDasharray="4 4" fill="none" strokeWidth={1} />
                  <Area type="monotone" dataKey="p90" stroke="hsl(173, 80%, 50%)" strokeOpacity={0.4} strokeDasharray="4 4" fill="none" strokeWidth={1} />
                </>
              )}
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <div className="flex gap-6 mt-4 justify-center text-xs font-mono text-muted-foreground flex-wrap">
          {!useMC ? (
             <>
               <div className="flex items-center gap-2"><div className="w-3 h-0.5 bg-primary rounded" /> Patrimônio nominal</div>
               <div className="flex items-center gap-2"><div className="w-3 h-0.5 bg-blue-400 rounded border-dashed" style={{ borderTop: "2px dashed" }} /> Patrimônio real (inflação {inflation}%)</div>
             </>
          ) : (
             <>
               <div className="flex items-center gap-2"><div className="w-3 h-0.5 bg-primary rounded" /> Mediana Estocástica (P50)</div>
               <div className="flex items-center gap-2"><div className="w-4 h-3 bg-primary/20 rounded border border-primary/40 border-dashed" /> Cone 80% (P10-P90)</div>
             </>
          )}
          <div className="flex items-center gap-2"><div className="w-3 h-0.5 bg-muted-foreground rounded" /> Total investido</div>
        </div>
      </div>
    </div>
  );
};

export default SimulatorPage;
