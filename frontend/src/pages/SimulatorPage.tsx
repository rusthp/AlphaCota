import { useState, useMemo, useEffect } from "react";
import { LineChart as LineChartIcon, DollarSign, Calendar, TrendingUp, Percent, Wallet } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Badge } from "@/components/ui/badge";
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { usePortfolio } from "@/hooks/use-portfolio";
import { useScanner } from "@/hooks/use-api";

const SimulatorPage = () => {
  const { portfolio, isEmpty: portfolioEmpty } = usePortfolio();
  const { data: scannerData } = useScanner();

  // Calculate real portfolio value and DY if portfolio exists
  const portfolioStats = useMemo(() => {
    if (portfolioEmpty || !scannerData) return null;
    const priceMap: Record<string, number> = {};
    const dyMap: Record<string, number> = {};
    scannerData.fiis.forEach((f) => {
      priceMap[f.ticker] = f.price;
      dyMap[f.ticker] = f.dy;
    });
    let totalValue = 0;
    let weightedDY = 0;
    for (const a of portfolio.assets) {
      const price = priceMap[a.ticker] || a.avgPrice;
      const value = a.quantity * price;
      const dy = dyMap[a.ticker] || 8;
      totalValue += value;
      weightedDY += value * dy;
    }
    return {
      totalValue: Math.round(totalValue),
      avgDY: totalValue > 0 ? weightedDY / totalValue : 9,
    };
  }, [portfolio.assets, scannerData, portfolioEmpty]);

  const [initialCapital, setInitialCapital] = useState(portfolioStats?.totalValue || 10000);
  const [monthlyInvestment, setMonthlyInvestment] = useState(1000);
  const [avgDY, setAvgDY] = useState(portfolioStats?.avgDY || 9);

  // Sync from portfolio when data loads
  useEffect(() => {
    if (portfolioStats) {
      setInitialCapital(portfolioStats.totalValue);
      setAvgDY(Math.round(portfolioStats.avgDY * 10) / 10);
    }
  }, [portfolioStats]);
  const [years, setYears] = useState(20);
  const [reinvest, setReinvest] = useState(true);

  const simulation = useMemo(() => {
    const monthlyDY = avgDY / 100 / 12;
    const data: { month: number; year: string; patrimony: number; income: number; invested: number }[] = [];
    let patrimony = initialCapital;
    let totalInvested = initialCapital;

    for (let m = 0; m <= years * 12; m++) {
      const monthlyIncome = patrimony * monthlyDY;
      if (m % 6 === 0) {
        data.push({
          month: m,
          year: `Ano ${Math.floor(m / 12)}`,
          patrimony: Math.round(patrimony),
          income: Math.round(monthlyIncome),
          invested: Math.round(totalInvested),
        });
      }
      if (reinvest) {
        patrimony += monthlyIncome;
      }
      patrimony += monthlyInvestment;
      totalInvested += monthlyInvestment;
    }
    return data;
  }, [initialCapital, monthlyInvestment, avgDY, years, reinvest]);

  const finalData = simulation[simulation.length - 1];
  const totalDividends = finalData.patrimony - finalData.invested;

  const formatCurrency = (v: number) =>
    v >= 1000000
      ? `R$ ${(v / 1000000).toFixed(1)}M`
      : v >= 1000
      ? `R$ ${(v / 1000).toFixed(0)}k`
      : `R$ ${v.toFixed(0)}`;

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-3">
          <LineChartIcon className="w-6 h-6 text-primary" />
          Simulador de Renda Passiva
        </h1>
        <p className="text-sm text-muted-foreground mt-1">Projete o crescimento da sua renda com FIIs ao longo do tempo</p>
        {portfolioStats && (
          <Badge variant="outline" className="mt-2 text-xs border-primary/30 text-primary">
            <Wallet className="w-3 h-3 mr-1" />
            Usando dados da sua carteira: R$ {portfolioStats.totalValue.toLocaleString()} | DY {portfolioStats.avgDY.toFixed(1)}%
          </Badge>
        )}
      </div>

      {/* Controls */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="glass-card p-6 space-y-6">
          <h3 className="font-semibold text-sm flex items-center gap-2">
            <DollarSign className="w-4 h-4 text-primary" /> Parâmetros
          </h3>

          <div className="space-y-4">
            <div>
              <label className="text-xs text-muted-foreground font-mono mb-2 flex justify-between">
                Capital Inicial
                <span className="text-foreground">R$ {initialCapital.toLocaleString()}</span>
              </label>
              <Slider
                value={[initialCapital]}
                onValueChange={([v]) => setInitialCapital(v)}
                min={0}
                max={500000}
                step={5000}
                className="py-2"
              />
            </div>

            <div>
              <label className="text-xs text-muted-foreground font-mono mb-2 flex justify-between">
                Aporte Mensal
                <span className="text-foreground">R$ {monthlyInvestment.toLocaleString()}</span>
              </label>
              <Slider
                value={[monthlyInvestment]}
                onValueChange={([v]) => setMonthlyInvestment(v)}
                min={0}
                max={20000}
                step={100}
                className="py-2"
              />
            </div>

            <div>
              <label className="text-xs text-muted-foreground font-mono mb-2 flex justify-between">
                Dividend Yield Médio
                <span className="text-foreground">{avgDY}% a.a.</span>
              </label>
              <Slider
                value={[avgDY]}
                onValueChange={([v]) => setAvgDY(v)}
                min={4}
                max={18}
                step={0.5}
                className="py-2"
              />
            </div>

            <div>
              <label className="text-xs text-muted-foreground font-mono mb-2 flex justify-between">
                Período
                <span className="text-foreground">{years} anos</span>
              </label>
              <Slider
                value={[years]}
                onValueChange={([v]) => setYears(v)}
                min={1}
                max={40}
                step={1}
                className="py-2"
              />
            </div>

            <div className="flex items-center justify-between pt-2">
              <span className="text-xs text-muted-foreground font-mono">Reinvestir dividendos</span>
              <Button
                size="sm"
                variant={reinvest ? "default" : "outline"}
                onClick={() => setReinvest(!reinvest)}
                className="text-xs h-7"
              >
                {reinvest ? "Sim ✓" : "Não"}
              </Button>
            </div>
          </div>
        </div>

        {/* Results cards */}
        <div className="grid grid-cols-2 gap-4 content-start">
          {[
            { label: "Patrimônio Final", value: formatCurrency(finalData.patrimony), icon: TrendingUp, highlight: true },
            { label: "Total Investido", value: formatCurrency(finalData.invested), icon: DollarSign },
            { label: "Renda Mensal Final", value: formatCurrency(finalData.income), icon: Calendar, highlight: true },
            { label: "Ganho com Dividendos", value: formatCurrency(totalDividends), icon: Percent },
          ].map((card) => (
            <div key={card.label} className={`glass-card p-4 ${card.highlight ? "glow-primary border-primary/20" : ""}`}>
              <div className="flex items-center gap-1.5 text-muted-foreground text-xs mb-2">
                <card.icon className="w-3.5 h-3.5 text-primary" />
                {card.label}
              </div>
              <div className="text-xl font-bold font-mono">{card.value}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Chart */}
      <div className="glass-card p-6">
        <h3 className="font-semibold text-sm mb-4">Projeção de Crescimento Patrimonial</h3>
        <div className="h-80">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={simulation}>
              <defs>
                <linearGradient id="gradPatrimony" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="hsl(173, 80%, 50%)" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="hsl(173, 80%, 50%)" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gradInvested" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="hsl(215, 20%, 55%)" stopOpacity={0.2} />
                  <stop offset="100%" stopColor="hsl(215, 20%, 55%)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(222, 30%, 16%)" />
              <XAxis
                dataKey="year"
                tick={{ fontSize: 11, fill: "hsl(215, 20%, 55%)" }}
                tickLine={false}
                axisLine={false}
                interval={Math.max(1, Math.floor(simulation.length / 8))}
              />
              <YAxis
                tick={{ fontSize: 11, fill: "hsl(215, 20%, 55%)" }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => v >= 1000000 ? `${(v / 1000000).toFixed(1)}M` : `${(v / 1000).toFixed(0)}k`}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "hsl(222, 44%, 9%)",
                  border: "1px solid hsl(222, 30%, 16%)",
                  borderRadius: "0.75rem",
                  fontFamily: "JetBrains Mono",
                  fontSize: 12,
                }}
                formatter={(value: number, name: string) => [
                  `R$ ${value.toLocaleString()}`,
                  name === "patrimony" ? "Patrimônio" : name === "invested" ? "Investido" : "Renda/mês",
                ]}
                labelStyle={{ color: "hsl(215, 20%, 55%)" }}
              />
              <Area type="monotone" dataKey="invested" stroke="hsl(215, 20%, 55%)" fill="url(#gradInvested)" strokeWidth={1.5} />
              <Area type="monotone" dataKey="patrimony" stroke="hsl(173, 80%, 50%)" fill="url(#gradPatrimony)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <div className="flex gap-6 mt-4 justify-center text-xs font-mono text-muted-foreground">
          <div className="flex items-center gap-2">
            <div className="w-3 h-0.5 bg-primary rounded" />
            Patrimônio
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-0.5 bg-muted-foreground rounded" />
            Total Investido
          </div>
        </div>
      </div>
    </div>
  );
};

export default SimulatorPage;
