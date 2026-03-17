import { useState, useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  TrendingUp, TrendingDown, Wallet, DollarSign,
  PieChart as PieIcon, RefreshCw, Plus, Trash2, User, Loader2, Shield
} from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { usePortfolio, calculateInvestorProfile } from "@/hooks/use-portfolio";
import { useScanner } from "@/hooks/use-api";

const SEGMENT_COLORS: Record<string, string> = {
  "Logística": "hsl(173, 80%, 50%)",
  "Shopping": "hsl(145, 70%, 50%)",
  "Híbrido": "hsl(210, 70%, 55%)",
  "Lajes Corp.": "hsl(280, 60%, 55%)",
  "Papel (CRI)": "hsl(45, 80%, 55%)",
  "Fundo de Fundos": "hsl(30, 70%, 55%)",
  "Agro": "hsl(90, 60%, 50%)",
  "Saúde": "hsl(0, 60%, 55%)",
  "Residencial": "hsl(320, 50%, 55%)",
};

export default function PortfolioPage() {
  const { portfolio, addAsset, removeAsset, updateAsset, isEmpty } = usePortfolio();
  const { data: scannerData, isLoading: scannerLoading } = useScanner();
  const [newTicker, setNewTicker] = useState("");
  const [newQty, setNewQty] = useState("");
  const [newPrice, setNewPrice] = useState("");
  const [editingTicker, setEditingTicker] = useState<string | null>(null);
  const [editQty, setEditQty] = useState("");
  const [editPrice, setEditPrice] = useState("");

  // Build sector map and price map from scanner data
  const sectorMap = useMemo(() => {
    const map: Record<string, string> = {};
    scannerData?.fiis?.forEach((f) => { map[f.ticker] = f.segment; });
    return map;
  }, [scannerData]);

  const priceMap = useMemo(() => {
    const map: Record<string, number> = {};
    scannerData?.fiis?.forEach((f) => { map[f.ticker] = f.price; });
    return map;
  }, [scannerData]);

  const dyMap = useMemo(() => {
    const map: Record<string, number> = {};
    scannerData?.fiis?.forEach((f) => { map[f.ticker] = f.dy; });
    return map;
  }, [scannerData]);

  // Enrich portfolio with live data
  const enrichedAssets = useMemo(() => {
    return portfolio.assets.map((a) => {
      const currentPrice = priceMap[a.ticker] || a.avgPrice;
      const dy = dyMap[a.ticker] || 0;
      const segment = sectorMap[a.ticker] || "Outros";
      const totalCost = a.quantity * a.avgPrice;
      const totalValue = a.quantity * currentPrice;
      const ret = a.avgPrice > 0 ? ((currentPrice - a.avgPrice) / a.avgPrice) * 100 : 0;
      const dividendMonthly = (totalValue * (dy / 100)) / 12;
      return {
        ...a,
        currentPrice,
        dy,
        segment,
        totalCost,
        totalValue,
        returnPct: ret,
        dividendMonthly,
      };
    });
  }, [portfolio.assets, priceMap, dyMap, sectorMap]);

  const totalEquity = enrichedAssets.reduce((s, a) => s + a.totalValue, 0);
  const totalCost = enrichedAssets.reduce((s, a) => s + a.totalCost, 0);
  const totalDividends = enrichedAssets.reduce((s, a) => s + a.dividendMonthly, 0);
  const totalReturn = totalCost > 0 ? ((totalEquity - totalCost) / totalCost) * 100 : 0;

  // Investor profile
  const profile = calculateInvestorProfile(portfolio.assets, sectorMap);

  // Sector allocation
  const segmentData = useMemo(() => {
    const map: Record<string, number> = {};
    enrichedAssets.forEach((a) => {
      const pct = totalEquity > 0 ? (a.totalValue / totalEquity) * 100 : 0;
      map[a.segment] = (map[a.segment] || 0) + pct;
    });
    return Object.entries(map).map(([name, value]) => ({ name, value: Math.round(value) }));
  }, [enrichedAssets, totalEquity]);

  // Available tickers for autocomplete
  const availableTickers = useMemo(() => {
    if (!scannerData) return [];
    const existing = new Set(portfolio.assets.map((a) => a.ticker));
    return scannerData.fiis.filter((f) => !existing.has(f.ticker)).map((f) => f.ticker);
  }, [scannerData, portfolio.assets]);

  const handleAdd = () => {
    const ticker = newTicker.toUpperCase().trim();
    const qty = parseInt(newQty);
    const price = parseFloat(newPrice) || priceMap[ticker] || 0;
    if (!ticker || !qty || qty <= 0) return;
    addAsset(ticker, qty, price);
    setNewTicker("");
    setNewQty("");
    setNewPrice("");
  };

  const handleStartEdit = (a: typeof enrichedAssets[0]) => {
    setEditingTicker(a.ticker);
    setEditQty(String(a.quantity));
    setEditPrice(String(a.avgPrice.toFixed(2)));
  };

  const handleSaveEdit = () => {
    if (!editingTicker) return;
    const qty = parseInt(editQty);
    const price = parseFloat(editPrice);
    if (qty > 0 && price > 0) {
      updateAsset(editingTicker, qty, price);
    }
    setEditingTicker(null);
  };

  if (scannerLoading) {
    return (
      <div className="flex items-center justify-center h-96 gap-3 text-muted-foreground">
        <Loader2 className="w-5 h-5 animate-spin" />
        Carregando dados do mercado...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold font-[family-name:var(--font-display)]">Minha Carteira</h1>
        <p className="text-muted-foreground text-sm mt-1">
          {isEmpty ? "Adicione seus FIIs para começar a análise" : `${portfolio.assets.length} ativos — preços atualizados em tempo real`}
        </p>
      </div>

      {/* Add asset form */}
      <Card className="bg-card border-border/30">
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-[family-name:var(--font-display)] flex items-center gap-2">
            <Plus className="w-4 h-4 text-primary" /> Adicionar FII
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="flex-1">
              <Input
                value={newTicker}
                onChange={(e) => setNewTicker(e.target.value.toUpperCase())}
                placeholder="Ticker (ex: HGLG11)"
                className="bg-secondary border-border/50 font-mono"
                list="ticker-list"
              />
              <datalist id="ticker-list">
                {availableTickers.map((t) => (
                  <option key={t} value={t} />
                ))}
              </datalist>
            </div>
            <Input
              type="number"
              value={newQty}
              onChange={(e) => setNewQty(e.target.value)}
              placeholder="Quantidade"
              className="bg-secondary border-border/50 font-mono w-32"
              min="1"
            />
            <Input
              type="number"
              value={newPrice}
              onChange={(e) => setNewPrice(e.target.value)}
              placeholder={newTicker && priceMap[newTicker.toUpperCase()] ? `R$ ${priceMap[newTicker.toUpperCase()]?.toFixed(2)} (atual)` : "Preço médio"}
              className="bg-secondary border-border/50 font-mono w-40"
              step="0.01"
            />
            <Button onClick={handleAdd} disabled={!newTicker.trim() || !newQty}>
              <Plus className="w-4 h-4 mr-1" /> Adicionar
            </Button>
          </div>
        </CardContent>
      </Card>

      {isEmpty ? (
        <Card className="bg-card border-border/30">
          <CardContent className="p-12 text-center">
            <Wallet className="w-12 h-12 text-muted-foreground/30 mx-auto mb-4" />
            <h3 className="text-lg font-semibold mb-2">Carteira vazia</h3>
            <p className="text-sm text-muted-foreground max-w-md mx-auto">
              Adicione seus FIIs acima para ver alocação por segmento, rentabilidade, dividendos estimados e perfil de investidor.
            </p>
          </CardContent>
        </Card>
      ) : (
        <>
          {/* KPI Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <Card className="bg-card border-border/30">
              <CardContent className="p-4">
                <div className="flex items-center gap-2 text-muted-foreground text-xs mb-1">
                  <Wallet className="w-3.5 h-3.5" /> Patrimônio
                </div>
                <p className="text-xl font-bold font-[family-name:var(--font-mono)]">
                  R$ {totalEquity.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                </p>
              </CardContent>
            </Card>
            <Card className="bg-card border-border/30">
              <CardContent className="p-4">
                <div className="flex items-center gap-2 text-muted-foreground text-xs mb-1">
                  <DollarSign className="w-3.5 h-3.5" /> Dividendos/mês (est.)
                </div>
                <p className="text-xl font-bold font-[family-name:var(--font-mono)] text-primary">
                  R$ {totalDividends.toFixed(2)}
                </p>
              </CardContent>
            </Card>
            <Card className="bg-card border-border/30">
              <CardContent className="p-4">
                <div className="flex items-center gap-2 text-muted-foreground text-xs mb-1">
                  <PieIcon className="w-3.5 h-3.5" /> Ativos
                </div>
                <p className="text-xl font-bold font-[family-name:var(--font-mono)]">{portfolio.assets.length}</p>
              </CardContent>
            </Card>
            <Card className="bg-card border-border/30">
              <CardContent className="p-4">
                <div className="flex items-center gap-2 text-muted-foreground text-xs mb-1">
                  {totalReturn >= 0 ? <TrendingUp className="w-3.5 h-3.5 text-accent" /> : <TrendingDown className="w-3.5 h-3.5 text-destructive" />}
                  Rentabilidade
                </div>
                <p className={`text-xl font-bold font-[family-name:var(--font-mono)] ${totalReturn >= 0 ? "text-accent" : "text-destructive"}`}>
                  {totalReturn >= 0 ? "+" : ""}{totalReturn.toFixed(2)}%
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Investor Profile + Allocation Chart */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Investor Profile */}
            <Card className="bg-card border-border/30">
              <CardHeader className="pb-2">
                <CardTitle className="text-base font-[family-name:var(--font-display)] flex items-center gap-2">
                  <User className="w-4 h-4 text-primary" /> Perfil do Investidor
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-center mb-4">
                  <div className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-primary/10 border border-primary/20">
                    <Shield className="w-5 h-5 text-primary" />
                    <span className="text-lg font-bold text-primary">{profile.profile}</span>
                  </div>
                </div>
                <p className="text-sm text-muted-foreground text-center mb-4">{profile.description}</p>
                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-muted-foreground">Conservador</span>
                    <span className="font-mono">{profile.riskLevel}/100</span>
                    <span className="text-muted-foreground">Agressivo</span>
                  </div>
                  <Progress value={profile.riskLevel} className="h-2" />
                </div>
              </CardContent>
            </Card>

            {/* Pie Chart */}
            <Card className="bg-card border-border/30">
              <CardHeader className="pb-2">
                <CardTitle className="text-base font-[family-name:var(--font-display)]">Alocação por Segmento</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-col sm:flex-row items-center gap-4">
                  <div className="w-48 h-48">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={segmentData}
                          cx="50%"
                          cy="50%"
                          innerRadius={45}
                          outerRadius={80}
                          paddingAngle={3}
                          dataKey="value"
                          stroke="none"
                        >
                          {segmentData.map((entry) => (
                            <Cell key={entry.name} fill={SEGMENT_COLORS[entry.name] || "hsl(var(--muted))"} />
                          ))}
                        </Pie>
                        <Tooltip
                          contentStyle={{
                            backgroundColor: "hsl(222, 44%, 9%)",
                            border: "1px solid hsl(222, 30%, 16%)",
                            borderRadius: "8px",
                            fontSize: "12px",
                          }}
                          formatter={(value: number) => [`${value}%`, "Peso"]}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="flex flex-col gap-2 text-sm">
                    {segmentData.map((s) => (
                      <div key={s.name} className="flex items-center gap-2">
                        <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: SEGMENT_COLORS[s.name] || "#888" }} />
                        <span className="text-muted-foreground">{s.name}</span>
                        <span className="font-[family-name:var(--font-mono)] font-medium ml-auto">{s.value}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Assets Table */}
          <Card className="bg-card border-border/30">
            <CardHeader className="pb-2">
              <CardTitle className="text-base font-[family-name:var(--font-display)]">Ativos na Carteira</CardTitle>
              <CardDescription>Clique em um ativo para editar. Preços atuais do mercado.</CardDescription>
            </CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow className="border-border/30 hover:bg-transparent">
                    <TableHead className="text-xs">Ticker</TableHead>
                    <TableHead className="text-xs hidden sm:table-cell">Segmento</TableHead>
                    <TableHead className="text-xs text-right">Qtd</TableHead>
                    <TableHead className="text-xs text-right hidden md:table-cell">PM</TableHead>
                    <TableHead className="text-xs text-right">Atual</TableHead>
                    <TableHead className="text-xs text-right">Retorno</TableHead>
                    <TableHead className="text-xs text-right hidden sm:table-cell">DY</TableHead>
                    <TableHead className="text-xs text-right">Div/mês</TableHead>
                    <TableHead className="text-xs text-center w-16"></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {enrichedAssets.map((a) => (
                    <TableRow key={a.ticker} className="border-border/30">
                      {editingTicker === a.ticker ? (
                        <>
                          <TableCell className="font-[family-name:var(--font-mono)] font-medium text-sm">{a.ticker}</TableCell>
                          <TableCell className="hidden sm:table-cell">
                            <Badge variant="outline" className="text-xs border-border/50">{a.segment}</Badge>
                          </TableCell>
                          <TableCell className="text-right">
                            <Input
                              type="number"
                              value={editQty}
                              onChange={(e) => setEditQty(e.target.value)}
                              className="w-20 h-7 text-xs font-mono bg-secondary"
                              min="1"
                            />
                          </TableCell>
                          <TableCell className="text-right hidden md:table-cell">
                            <Input
                              type="number"
                              value={editPrice}
                              onChange={(e) => setEditPrice(e.target.value)}
                              className="w-24 h-7 text-xs font-mono bg-secondary"
                              step="0.01"
                            />
                          </TableCell>
                          <TableCell colSpan={3}></TableCell>
                          <TableCell className="text-center">
                            <Button size="sm" variant="ghost" className="h-7 text-xs text-primary" onClick={handleSaveEdit}>
                              Salvar
                            </Button>
                          </TableCell>
                        </>
                      ) : (
                        <>
                          <TableCell
                            className="font-[family-name:var(--font-mono)] font-medium text-sm cursor-pointer hover:text-primary"
                            onClick={() => handleStartEdit(a)}
                          >
                            {a.ticker}
                          </TableCell>
                          <TableCell className="hidden sm:table-cell">
                            <Badge variant="outline" className="text-xs border-border/50">{a.segment}</Badge>
                          </TableCell>
                          <TableCell className="text-right font-[family-name:var(--font-mono)] text-sm">{a.quantity}</TableCell>
                          <TableCell className="text-right font-[family-name:var(--font-mono)] text-sm hidden md:table-cell">
                            R$ {a.avgPrice.toFixed(2)}
                          </TableCell>
                          <TableCell className="text-right font-[family-name:var(--font-mono)] text-sm">
                            R$ {a.currentPrice.toFixed(2)}
                          </TableCell>
                          <TableCell className={`text-right font-[family-name:var(--font-mono)] text-sm font-medium ${a.returnPct >= 0 ? "text-accent" : "text-destructive"}`}>
                            {a.returnPct >= 0 ? "+" : ""}{a.returnPct.toFixed(1)}%
                          </TableCell>
                          <TableCell className="text-right font-[family-name:var(--font-mono)] text-sm text-primary hidden sm:table-cell">
                            {a.dy.toFixed(1)}%
                          </TableCell>
                          <TableCell className="text-right font-[family-name:var(--font-mono)] text-sm">
                            R$ {a.dividendMonthly.toFixed(2)}
                          </TableCell>
                          <TableCell className="text-center">
                            <Button
                              size="sm"
                              variant="ghost"
                              className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                              onClick={() => removeAsset(a.ticker)}
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </Button>
                          </TableCell>
                        </>
                      )}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
