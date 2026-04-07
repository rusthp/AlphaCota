import { useState, useRef, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Bot, Send, User, Sparkles, TrendingUp, Building2, PieChart, Lightbulb, Activity, CheckCircle2, AlertTriangle, AlertCircle, RefreshCw, ArrowUpRight, ArrowDownRight, ArrowRight } from "lucide-react";
import { usePortfolio } from "@/hooks/use-portfolio";
import { useAIBatchAnalysis, useAIAnalysis, useSentimentTrend } from "@/hooks/use-api";
import { AIAnalysisResult } from "@/services/api";

interface Message {
  role: "user" | "assistant";
  content: string;
}

const suggestedQuestions = [
  { icon: TrendingUp, text: "Analise HGLG11" },
  { icon: Building2, text: "Analise MXRF11" },
  { icon: PieChart, text: "Analise XPML11" },
  { icon: Lightbulb, text: "Analise BTLG11" },
];

function extractTicker(input: string): string | null {
  const match = input.match(/\b([A-Z]{4}\d{2})\b/i);
  return match ? match[1].toUpperCase() : null;
}

function Semaphore({ score }: { score?: number }) {
  if (score === undefined || score === null) return <Badge variant="outline"><AlertCircle className="w-3 h-3 mr-1" /> Desconhecido</Badge>;
  if (score > 0) return <Badge className="bg-green-500/20 text-green-500 border-green-500/30 hover:bg-green-500/20"><CheckCircle2 className="w-3 h-3 mr-1" /> Positivo</Badge>;
  if (score < 0) return <Badge variant="destructive" className="bg-red-500/20 text-red-500 border-red-500/30 hover:bg-red-500/20"><AlertTriangle className="w-3 h-3 mr-1" /> Negativo</Badge>;
  return <Badge variant="secondary" className="bg-yellow-500/20 text-yellow-500 border-yellow-500/30 hover:bg-yellow-500/20"><AlertCircle className="w-3 h-3 mr-1" /> Neutro</Badge>;
}

function SentimentTrendLine({ ticker }: { ticker: string }) {
  const { data, isLoading } = useSentimentTrend(ticker, 5);

  if (isLoading || !data?.trend) return <span className="text-xs text-muted-foreground ml-2">⏳</span>;
  if (data.trend.length < 2) return null; // Sem histórico

  const reversed = [...data.trend].reverse(); // cronológico: mais antigo [0], mais novo [length-1]
  const latest = reversed[reversed.length - 1].sentiment;
  const previous = reversed[reversed.length - 2].sentiment;

  const weight = (s: string) => s === "POSITIVO" ? 1 : s === "NEGATIVO" ? -1 : 0;
  
  const diff = weight(latest) - weight(previous);

  if (diff > 0) return <Badge variant="outline" className="ml-2 bg-green-500/10 text-green-500 border-green-500/30 font-mono text-[10px] h-5 px-1.5"><ArrowUpRight className="w-3 h-3 mr-0.5" /> Reversão Positiva</Badge>;
  if (diff < 0) return <Badge variant="outline" className="ml-2 bg-red-500/10 text-red-500 border-red-500/30 font-mono text-[10px] h-5 px-1.5"><ArrowDownRight className="w-3 h-3 mr-0.5" /> Reversão Negativa</Badge>;

  return <Badge variant="outline" className="ml-2 bg-secondary/50 text-muted-foreground border-border/50 font-mono text-[10px] h-5 px-1.5"><ArrowRight className="w-3 h-3 mr-0.5" /> Estável</Badge>;
}

export default function AIInsightsPage() {
  const { portfolio } = usePortfolio();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  
  const aiAnalysis = useAIAnalysis();
  const batchAnalysis = useAIBatchAnalysis();

  const [batchResults, setBatchResults] = useState<AIAnalysisResult[]>([]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const sendMessage = async (text: string) => {
    if (!text.trim() || aiAnalysis.isPending) return;

    const userMsg: Message = { role: "user", content: text.trim() };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");

    const ticker = extractTicker(text);

    try {
      if (ticker) {
        const result = await aiAnalysis.mutateAsync({ ticker });
        let response: string;

        if (result.success && result.raw_response) {
          const newsSection = result.news && result.news.length > 0
            ? `\n\n### Notícias Analisadas (${result.news_count})\n${result.news.map((n) => `- ${n.titulo} (${n.data})`).join("\n")}`
            : "";
          response = result.raw_response + newsSection;
        } else {
          response = `**Análise de ${ticker}**\n\n${result.error || "Não foi possível gerar análise."}\n\nVerifique se a chave GROQ_API_KEY está configurada no ambiente.`;
        }
        setMessages((prev) => [...prev, { role: "assistant", content: response }]);
      } else {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: "Para gerar uma análise com IA, mencione um **ticker de FII** (ex: HGLG11, MXRF11, XPML11).",
          },
        ]);
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `**Erro ao analisar:** ${(err as Error).message}`,
        },
      ]);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    sendMessage(input);
  };

  const handleBatchAnalysis = async () => {
    if (portfolio.assets.length === 0) return;
    const tickers = portfolio.assets.map(a => a.ticker);
    try {
      const res = await batchAnalysis.mutateAsync({ tickers });
      if (res.success && res.results) {
        setBatchResults(res.results);
      }
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)]">
      {/* Header */}
      <div className="pb-4">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-primary/20 flex items-center justify-center">
            <Sparkles className="w-4 h-4 text-primary" />
          </div>
          <div>
            <h1 className="text-xl font-bold font-[family-name:var(--font-display)]">AI Insights</h1>
            <p className="text-xs text-muted-foreground">Análise de sentimento com Llama + noticias reais (Cache 6h)</p>
          </div>
        </div>
      </div>

      <Tabs defaultValue="chat" className="flex-1 flex flex-col min-h-0">
        <div className="px-1 border-b border-border/40">
          <TabsList className="bg-transparent h-10 p-0 rounded-none w-full justify-start gap-4">
            <TabsTrigger value="chat" className="data-[state=active]:bg-transparent data-[state=active]:shadow-none data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none px-2 h-10">
              <Bot className="w-4 h-4 mr-2" />
              Chat Interativo
            </TabsTrigger>
            <TabsTrigger value="batch" className="data-[state=active]:bg-transparent data-[state=active]:shadow-none data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none px-2 h-10">
              <PieChart className="w-4 h-4 mr-2" />
              Análise da Carteira
            </TabsTrigger>
          </TabsList>
        </div>

        {/* --- ABA 1: CHAT --- */}
        <TabsContent value="chat" className="flex-1 flex flex-col mt-4 border border-border/30 rounded-xl overflow-hidden bg-card data-[state=inactive]:hidden">
          <ScrollArea className="flex-1 p-4" ref={scrollRef}>
            {messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full min-h-[300px] text-center">
                <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mb-4">
                  <Sparkles className="w-8 h-8 text-primary" />
                </div>
                <h2 className="text-lg font-semibold font-[family-name:var(--font-display)] mb-2">Assistente de Investimentos</h2>
                <p className="text-sm text-muted-foreground mb-6 max-w-md">Informe um ticker de FII para receber análise de sentimento baseada em notícias reais.</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-lg">
                  {suggestedQuestions.map((q, i) => (
                    <button key={i} onClick={() => sendMessage(q.text)} className="flex items-start gap-2.5 p-3 rounded-lg bg-secondary/50 border border-border/30 text-left text-sm hover:bg-secondary/80 transition-colors">
                      <q.icon className="w-4 h-4 text-primary mt-0.5 shrink-0" />
                      <span className="text-muted-foreground">{q.text}</span>
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                {messages.map((msg, i) => (
                  <div key={i} className={`flex gap-3 ${msg.role === "user" ? "justify-end" : ""}`}>
                    {msg.role === "assistant" && (
                      <div className="w-7 h-7 rounded-lg bg-primary/20 flex items-center justify-center shrink-0 mt-1">
                        <Bot className="w-3.5 h-3.5 text-primary" />
                      </div>
                    )}
                    <div className={`max-w-[85%] rounded-xl px-4 py-3 text-sm flex-col ${msg.role === "user" ? "bg-primary text-primary-foreground" : "bg-secondary/50 border border-border/30 overflow-hidden"}`}>
                      {msg.role === "assistant" ? (
                        <div className="prose prose-sm prose-invert max-w-none text-muted-foreground [&_strong]:text-foreground" dangerouslySetInnerHTML={{
                            __html: msg.content
                              .replace(/^### (.*$)/gm, '<h3>$1</h3>')
                              .replace(/^## (.*$)/gm, '<h2>$1</h2>')
                              .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                              .replace(/^\- (.*$)/gm, '<li>$1</li>')
                              .replace(/\n\n/g, '</p><p>')
                              .replace(/\n/g, '<br/>')
                        }} />
                      ) : (
                        <p>{msg.content}</p>
                      )}
                    </div>
                    {msg.role === "user" && <div className="w-7 h-7 rounded-lg bg-secondary flex items-center justify-center shrink-0 mt-1"><User className="w-3.5 h-3.5 text-muted-foreground" /></div>}
                  </div>
                ))}
                {aiAnalysis.isPending && (
                  <div className="flex gap-3">
                    <div className="w-7 h-7 rounded-lg bg-primary/20 flex items-center justify-center shrink-0"><Bot className="w-3.5 h-3.5 text-primary" /></div>
                    <div className="bg-secondary/50 border border-border/30 rounded-xl px-4 py-3"><div className="w-2 h-2 rounded-full bg-primary/50 animate-bounce" /></div>
                  </div>
                )}
              </div>
            )}
          </ScrollArea>
          <CardContent className="p-3 border-t border-border/30">
            <form onSubmit={handleSubmit} className="flex gap-2">
              <Input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Exemplo: Cotação e risco do XPML11"
                className="bg-secondary border-border/50"
                disabled={aiAnalysis.isPending}
              />
              <Button type="submit" size="icon" disabled={!input.trim() || aiAnalysis.isPending} className="shrink-0"><Send className="w-4 h-4" /></Button>
            </form>
          </CardContent>
        </TabsContent>

        {/* --- ABA 2: BATCH PORTFOLIO --- */}
        <TabsContent value="batch" className="flex-1 overflow-auto mt-4 data-[state=inactive]:hidden">
          <div className="mb-6 flex flex-col md:flex-row justify-between items-start md:items-center gap-4 bg-secondary/30 border border-border/40 p-5 rounded-xl">
             <div>
               <h2 className="font-semibold text-lg flex items-center gap-2"><Activity className="w-5 h-5 text-primary"/> Sentimento da Carteira</h2>
               <p className="text-sm text-muted-foreground">Mapeando emoções do mercado para {portfolio.assets.length} ativos ({portfolio.assets.map(a => a.ticker).join(", ")}).</p>
             </div>
             <Button onClick={handleBatchAnalysis} disabled={portfolio.assets.length === 0 || batchAnalysis.isPending}>
               {batchAnalysis.isPending ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : <Sparkles className="w-4 h-4 mr-2" />}
               Analisar Todos os Ativos
             </Button>
          </div>

          {!batchAnalysis.isPending && batchResults.length > 0 && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
               {batchResults.map((res, i) => (
                 <Card key={i} className="bg-card border-border/30">
                    <CardContent className="p-4">
                       <div className="flex justify-between items-start mb-3">
                          <div className="flex items-center">
                            <h3 className="font-bold text-lg">{res.ticker}</h3>
                            <SentimentTrendLine ticker={res.ticker} />
                          </div>
                          <div className="flex items-center gap-2">
                            {res.cached && <Badge variant="outline" className="text-[10px] uppercase h-5 text-muted-foreground">Em Cache</Badge>}
                            <Semaphore score={res.sentiment_score} />
                          </div>
                       </div>
                       
                       {res.success && res.raw_response ? (
                         <div className="text-sm text-muted-foreground bg-secondary/30 p-3 rounded-lg border border-border/20 line-clamp-4">
                           {res.raw_response}
                         </div>
                       ) : (
                         <div className="text-sm text-red-400">
                           {res.error || "Erro ao coletar notícias/sentimento"}
                         </div>
                       )}
                    </CardContent>
                 </Card>
               ))}
            </div>
          )}

          {!batchAnalysis.isPending && batchResults.length === 0 && portfolio.assets.length > 0 && (
            <div className="text-center py-10 opacity-60">
               <Bot className="w-10 h-10 mx-auto mb-3 opacity-50" />
               <p>Clique no botão acima para submeter a lista de FIIs ao modelo LLM.</p>
            </div>
          )}
          
          {portfolio.assets.length === 0 && (
             <div className="text-center py-10 text-muted-foreground">
                Sua carteira está vazia. Adicione ativos no Simulador para analisá-los em lote.
             </div>
          )}
        </TabsContent>

      </Tabs>
    </div>
  );
}
