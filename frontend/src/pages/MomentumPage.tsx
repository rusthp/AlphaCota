import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { TrendingUp, TrendingDown, Loader2, Zap } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { useMomentum } from "@/hooks/use-api";
import { useNavigate } from "react-router-dom";

export default function MomentumPage() {
  const { data, isLoading, error } = useMomentum(20);
  const navigate = useNavigate();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96 gap-3 text-muted-foreground">
        <Loader2 className="w-5 h-5 animate-spin" />
        Calculando momentum dos FIIs...
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 text-center text-destructive">
        <p>Erro: {(error as Error).message}</p>
      </div>
    );
  }

  const ranking = data?.ranking || [];
  const maxScore = Math.max(...ranking.map((r) => r.score), 1);

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-3">
          <Zap className="w-6 h-6 text-primary" />
          Momentum Ranking
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Ranking por retorno acumulado (3M, 6M, 12M ponderado) — {data?.total_analyzed || 0} FIIs analisados
        </p>
        <Badge variant="outline" className="mt-2 text-xs border-primary/30 text-primary">
          Dados reais via yfinance
        </Badge>
      </div>

      <Card className="bg-card border-border/30">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Top {ranking.length} por Momentum</CardTitle>
          <CardDescription>Score ponderado: 20% ret 3M + 30% ret 6M + 50% ret 12M</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="border-border/30 hover:bg-transparent">
                <TableHead className="text-xs w-12">#</TableHead>
                <TableHead className="text-xs">Ticker</TableHead>
                <TableHead className="text-xs text-right">Ret 3M</TableHead>
                <TableHead className="text-xs text-right">Ret 6M</TableHead>
                <TableHead className="text-xs text-right">Ret 12M</TableHead>
                <TableHead className="text-xs text-right">Score</TableHead>
                <TableHead className="text-xs w-32"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {ranking.map((r, i) => {
                const score = r.score || 0;
                const ret3 = (r.ret_3m || 0) * 100;
                const ret6 = (r.ret_6m || 0) * 100;
                const ret12 = (r.ret_12m || 0) * 100;
                return (
                  <TableRow
                    key={r.ticker}
                    className="border-border/30 cursor-pointer hover:bg-secondary/30"
                    onClick={() => navigate(`/dashboard/fii/${r.ticker}`)}
                  >
                    <TableCell className="font-mono text-muted-foreground">{i + 1}</TableCell>
                    <TableCell className="font-mono font-semibold">{r.ticker}</TableCell>
                    <TableCell className={`text-right font-mono text-sm ${ret3 >= 0 ? "text-accent" : "text-destructive"}`}>
                      {ret3 >= 0 ? "+" : ""}{ret3.toFixed(1)}%
                    </TableCell>
                    <TableCell className={`text-right font-mono text-sm ${ret6 >= 0 ? "text-accent" : "text-destructive"}`}>
                      {ret6 >= 0 ? "+" : ""}{ret6.toFixed(1)}%
                    </TableCell>
                    <TableCell className={`text-right font-mono text-sm ${ret12 >= 0 ? "text-accent" : "text-destructive"}`}>
                      {ret12 >= 0 ? "+" : ""}{ret12.toFixed(1)}%
                    </TableCell>
                    <TableCell className="text-right font-mono font-bold text-sm">
                      {(score * 100).toFixed(1)}
                    </TableCell>
                    <TableCell>
                      <Progress value={maxScore > 0 ? (score / maxScore) * 100 : 0} className="h-1.5" />
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
