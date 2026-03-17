import { useState, useRef, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Bot, Send, User, Sparkles, TrendingUp, Building2, PieChart, Lightbulb } from "lucide-react";
import { fetchAIAnalysis } from "@/services/api";

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

// Extract ticker from user input
function extractTicker(input: string): string | null {
  const match = input.match(/\b([A-Z]{4}\d{2})\b/i);
  return match ? match[1].toUpperCase() : null;
}

export default function AIInsightsPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const sendMessage = async (text: string) => {
    if (!text.trim() || isLoading) return;

    const userMsg: Message = { role: "user", content: text.trim() };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsLoading(true);

    const ticker = extractTicker(text);

    try {
      if (ticker) {
        const result = await fetchAIAnalysis(ticker);
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
            content:
              "Para gerar uma análise com IA, mencione um **ticker de FII** (ex: HGLG11, MXRF11, XPML11).\n\nA análise usa dados reais de notícias + o modelo Llama via Groq para gerar sentimento e insights.",
          },
        ]);
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `**Erro ao analisar:** ${(err as Error).message}\n\nVerifique se a API está rodando (python -m uvicorn api.main:app --port 8000).`,
        },
      ]);
    }

    setIsLoading(false);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    sendMessage(input);
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
            <p className="text-xs text-muted-foreground">Análise de sentimento com Groq/Llama + notícias reais via RSS</p>
          </div>
        </div>
        <Badge variant="outline" className="mt-2 text-xs border-primary/30 text-primary">
          <Bot className="w-3 h-3 mr-1" /> Live Mode — Dados reais + AI
        </Badge>
      </div>

      {/* Chat Area */}
      <Card className="flex-1 bg-card border-border/30 flex flex-col overflow-hidden">
        <ScrollArea className="flex-1 p-4" ref={scrollRef}>
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full min-h-[300px] text-center">
              <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mb-4">
                <Sparkles className="w-8 h-8 text-primary" />
              </div>
              <h2 className="text-lg font-semibold font-[family-name:var(--font-display)] mb-2">
                Assistente de Investimentos
              </h2>
              <p className="text-sm text-muted-foreground mb-6 max-w-md">
                Informe um ticker de FII para receber análise de sentimento baseada em notícias reais, processada pela IA (Groq/Llama).
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-lg">
                {suggestedQuestions.map((q, i) => (
                  <button
                    key={i}
                    onClick={() => sendMessage(q.text)}
                    className="flex items-start gap-2.5 p-3 rounded-lg bg-secondary/50 border border-border/30 text-left text-sm hover:bg-secondary/80 transition-colors"
                  >
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
                  <div className={`max-w-[85%] rounded-xl px-4 py-3 text-sm ${
                    msg.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : "bg-secondary/50 border border-border/30"
                  }`}>
                    {msg.role === "assistant" ? (
                      <div className="prose prose-sm prose-invert max-w-none
                        [&_h2]:text-base [&_h2]:font-semibold [&_h2]:mb-2 [&_h2]:mt-0
                        [&_h3]:text-sm [&_h3]:font-semibold [&_h3]:mb-1.5 [&_h3]:mt-3
                        [&_p]:mb-2 [&_p]:leading-relaxed
                        [&_ul]:mb-2 [&_ul]:space-y-1
                        [&_li]:text-muted-foreground
                        [&_strong]:text-foreground
                      ">
                        <div dangerouslySetInnerHTML={{
                          __html: msg.content
                            .replace(/^### (.*$)/gm, '<h3>$1</h3>')
                            .replace(/^## (.*$)/gm, '<h2>$1</h2>')
                            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                            .replace(/\*(.*?)\*/g, '<em>$1</em>')
                            .replace(/`(.*?)`/g, '<code>$1</code>')
                            .replace(/^\- (.*$)/gm, '<li>$1</li>')
                            .replace(/^(\d+)\. (.*$)/gm, '<li>$1. $2</li>')
                            .replace(/\n\n/g, '</p><p>')
                            .replace(/\n/g, '<br/>')
                        }} />
                      </div>
                    ) : (
                      <p>{msg.content}</p>
                    )}
                  </div>
                  {msg.role === "user" && (
                    <div className="w-7 h-7 rounded-lg bg-secondary flex items-center justify-center shrink-0 mt-1">
                      <User className="w-3.5 h-3.5 text-muted-foreground" />
                    </div>
                  )}
                </div>
              ))}
              {isLoading && (
                <div className="flex gap-3">
                  <div className="w-7 h-7 rounded-lg bg-primary/20 flex items-center justify-center shrink-0">
                    <Bot className="w-3.5 h-3.5 text-primary" />
                  </div>
                  <div className="bg-secondary/50 border border-border/30 rounded-xl px-4 py-3">
                    <div className="flex gap-1.5">
                      <div className="w-2 h-2 rounded-full bg-primary/50 animate-bounce" style={{ animationDelay: "0ms" }} />
                      <div className="w-2 h-2 rounded-full bg-primary/50 animate-bounce" style={{ animationDelay: "150ms" }} />
                      <div className="w-2 h-2 rounded-full bg-primary/50 animate-bounce" style={{ animationDelay: "300ms" }} />
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </ScrollArea>

        {/* Input */}
        <CardContent className="p-3 border-t border-border/30">
          <form onSubmit={handleSubmit} className="flex gap-2">
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Digite um ticker de FII para análise (ex: HGLG11)..."
              className="bg-secondary border-border/50"
              disabled={isLoading}
            />
            <Button type="submit" size="icon" disabled={!input.trim() || isLoading} className="shrink-0">
              <Send className="w-4 h-4" />
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
