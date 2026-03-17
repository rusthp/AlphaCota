import { Loader2, Layers, AlertTriangle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useClusters } from "@/hooks/use-api";

const CLUSTER_COLORS = [
  "bg-primary/20 text-primary border-primary/30",
  "bg-accent/20 text-accent border-accent/30",
  "bg-orange-500/20 text-orange-400 border-orange-500/30",
  "bg-purple-500/20 text-purple-400 border-purple-500/30",
  "bg-pink-500/20 text-pink-400 border-pink-500/30",
];

export default function ClustersPage() {
  const { data, isLoading, error } = useClusters();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96 gap-3 text-muted-foreground">
        <Loader2 className="w-5 h-5 animate-spin" />
        Agrupando FIIs por comportamento...
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 max-w-5xl mx-auto">
        <Card className="bg-destructive/10 border-destructive/30">
          <CardContent className="p-12 text-center">
            <AlertTriangle className="w-12 h-12 text-destructive/50 mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-destructive mb-2">Erro no Clustering</h3>
            <p className="text-sm text-muted-foreground">{(error as Error).message}</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Parse cluster data — format: { clusters: { "0": [...tickers], "1": [...] }, centroids: {...}, stats: {...} }
  const clusters: Record<string, string[]> = (data as Record<string, unknown>)?.clusters as Record<string, string[]> ?? {};
  const stats: Record<string, unknown> = (data as Record<string, unknown>)?.stats as Record<string, unknown> ?? {};
  const clusterKeys = Object.keys(clusters).sort();
  const totalFIIs = clusterKeys.reduce((sum, k) => sum + (clusters[k]?.length || 0), 0);

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-3">
          <Layers className="w-6 h-6 text-primary" />
          Clustering de FIIs
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Agrupamento por comportamento via K-Means — {totalFIIs} FIIs em {clusterKeys.length} clusters
        </p>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="glass-card p-4">
          <div className="text-xs text-muted-foreground mb-1">FIIs Analisados</div>
          <div className="text-xl font-bold font-mono">{totalFIIs}</div>
        </div>
        <div className="glass-card p-4">
          <div className="text-xs text-muted-foreground mb-1">Clusters</div>
          <div className="text-xl font-bold font-mono">{clusterKeys.length}</div>
        </div>
        <div className="glass-card p-4">
          <div className="text-xs text-muted-foreground mb-1">Maior Cluster</div>
          <div className="text-xl font-bold font-mono">
            {Math.max(...clusterKeys.map((k) => clusters[k]?.length || 0))} FIIs
          </div>
        </div>
        <div className="glass-card p-4">
          <div className="text-xs text-muted-foreground mb-1">Menor Cluster</div>
          <div className="text-xl font-bold font-mono">
            {Math.min(...clusterKeys.map((k) => clusters[k]?.length || 0))} FIIs
          </div>
        </div>
      </div>

      {/* Cluster cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {clusterKeys.map((key, idx) => {
          const members = clusters[key] || [];
          const colorClass = CLUSTER_COLORS[idx % CLUSTER_COLORS.length];

          return (
            <Card key={key} className="bg-card border-border/30">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Layers className="w-4 h-4 text-primary" />
                    Cluster {parseInt(key) + 1}
                  </div>
                  <Badge variant="outline" className="text-xs">
                    {members.length} FIIs
                  </Badge>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-1.5">
                  {members.map((ticker: string) => (
                    <span
                      key={ticker}
                      className={`px-2 py-0.5 rounded text-xs font-mono border ${colorClass}`}
                    >
                      {ticker}
                    </span>
                  ))}
                </div>
                <p className="text-[10px] text-muted-foreground mt-3">
                  {members.length} FIIs com comportamento de retorno semelhante
                </p>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Stats if available */}
      {stats && Object.keys(stats).length > 0 && (
        <Card className="bg-card border-border/30">
          <CardHeader>
            <CardTitle className="text-sm">Estatísticas do Clustering</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
              {Object.entries(stats).map(([key, val]) => (
                <div key={key}>
                  <span className="text-xs text-muted-foreground">{key}</span>
                  <div className="font-mono font-medium">
                    {typeof val === "number" ? val.toFixed(4) : String(val)}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
