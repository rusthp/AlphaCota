import { useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { useWatchlists } from "@/hooks/use-portfolio";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Bookmark,
  Plus,
  Trash2,
  X,
  Pencil,
  Check,
  ExternalLink,
} from "lucide-react";

export default function WatchlistPage() {
  const {
    watchlists,
    createList,
    deleteList,
    renameList,
    addTicker,
    removeTicker,
  } = useWatchlists();

  const [activeListId, setActiveListId] = useState<string>(() => watchlists[0]?.id ?? "");
  const [newListName, setNewListName] = useState("");
  const [tickerInput, setTickerInput] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");

  const activeList = watchlists.find(l => l.id === activeListId);

  const handleCreateList = useCallback(() => {
    const name = newListName.trim();
    if (!name) return;
    const id = createList(name);
    setActiveListId(id);
    setNewListName("");
  }, [newListName, createList]);

  const handleDeleteList = useCallback((id: string) => {
    deleteList(id);
    if (activeListId === id) {
      setActiveListId(watchlists.find(l => l.id !== id)?.id ?? "");
    }
  }, [deleteList, activeListId, watchlists]);

  const handleAddTicker = useCallback(() => {
    const t = tickerInput.trim().toUpperCase();
    if (!t || !activeListId) return;
    addTicker(activeListId, t);
    setTickerInput("");
  }, [tickerInput, activeListId, addTicker]);

  const handleRenameConfirm = useCallback((id: string) => {
    const name = editingName.trim();
    if (name) renameList(id, name);
    setEditingId(null);
  }, [editingName, renameList]);

  const startEdit = useCallback((id: string, currentName: string) => {
    setEditingId(id);
    setEditingName(currentName);
  }, []);

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
          <Bookmark className="h-6 w-6 text-primary" />
          Watchlists
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Organize FIIs em listas personalizadas para monitoramento
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Left: list selector */}
        <div className="md:col-span-1 space-y-3">
          <Card className="glass-card">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Minhas Listas</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1">
              {watchlists.length === 0 && (
                <p className="text-xs text-muted-foreground py-2">Nenhuma lista criada.</p>
              )}
              {watchlists.map(list => (
                <div
                  key={list.id}
                  className={`flex items-center gap-2 rounded-lg px-3 py-2 cursor-pointer transition-colors group ${
                    activeListId === list.id
                      ? "bg-primary/10 text-primary"
                      : "hover:bg-secondary/50 text-foreground"
                  }`}
                  onClick={() => setActiveListId(list.id)}
                >
                  {editingId === list.id ? (
                    <>
                      <Input
                        value={editingName}
                        onChange={e => setEditingName(e.target.value)}
                        onKeyDown={e => {
                          if (e.key === "Enter") handleRenameConfirm(list.id);
                          if (e.key === "Escape") setEditingId(null);
                        }}
                        className="h-6 text-xs py-0 px-1 flex-1"
                        autoFocus
                        onClick={e => e.stopPropagation()}
                      />
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-5 w-5 shrink-0"
                        onClick={e => { e.stopPropagation(); handleRenameConfirm(list.id); }}
                      >
                        <Check className="h-3 w-3" />
                      </Button>
                    </>
                  ) : (
                    <>
                      <span className="flex-1 text-sm truncate">{list.name}</span>
                      <Badge variant="secondary" className="text-[10px] h-4 px-1 shrink-0">
                        {list.tickers.length}
                      </Badge>
                      <div className="hidden group-hover:flex items-center gap-0.5">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-5 w-5"
                          onClick={e => { e.stopPropagation(); startEdit(list.id, list.name); }}
                        >
                          <Pencil className="h-3 w-3" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-5 w-5 text-destructive/70 hover:text-destructive"
                          onClick={e => { e.stopPropagation(); handleDeleteList(list.id); }}
                        >
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                    </>
                  )}
                </div>
              ))}
            </CardContent>
          </Card>

          {/* Create new list */}
          <Card className="glass-card">
            <CardContent className="pt-4 space-y-2">
              <p className="text-xs font-medium text-muted-foreground">Nova lista</p>
              <div className="flex gap-2">
                <Input
                  placeholder="Nome da lista..."
                  value={newListName}
                  onChange={e => setNewListName(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && handleCreateList()}
                  className="h-8 text-sm"
                />
                <Button size="sm" className="h-8 px-2 shrink-0" onClick={handleCreateList} disabled={!newListName.trim()}>
                  <Plus className="h-4 w-4" />
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Right: tickers in active list */}
        <div className="md:col-span-2">
          {!activeList ? (
            <Card className="glass-card">
              <CardContent className="py-16 text-center text-muted-foreground text-sm">
                Crie ou selecione uma lista para começar.
              </CardContent>
            </Card>
          ) : (
            <Card className="glass-card">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base font-semibold">{activeList.name}</CardTitle>
                  <span className="text-xs text-muted-foreground">
                    {activeList.tickers.length} FII{activeList.tickers.length !== 1 ? "s" : ""}
                  </span>
                </div>
                {/* Add ticker */}
                <div className="flex gap-2 mt-2">
                  <Input
                    placeholder="Ticker (ex: MXRF11)..."
                    value={tickerInput}
                    onChange={e => setTickerInput(e.target.value.toUpperCase())}
                    onKeyDown={e => e.key === "Enter" && handleAddTicker()}
                    className="h-8 text-sm font-mono uppercase"
                  />
                  <Button size="sm" className="h-8 shrink-0" onClick={handleAddTicker} disabled={!tickerInput.trim()}>
                    <Plus className="h-4 w-4 mr-1" /> Adicionar
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                {activeList.tickers.length === 0 ? (
                  <div className="py-12 text-center text-muted-foreground text-sm">
                    <Bookmark className="h-8 w-8 mx-auto mb-2 opacity-30" />
                    <p>Nenhum FII nesta lista ainda.</p>
                    <p className="text-xs mt-1">Digite um ticker acima para adicionar.</p>
                  </div>
                ) : (
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                    {activeList.tickers.map(ticker => (
                      <div
                        key={ticker}
                        className="flex items-center justify-between rounded-lg border border-border/50 bg-secondary/30 px-3 py-2 group"
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="font-mono text-sm font-semibold text-foreground truncate">
                            {ticker}
                          </span>
                        </div>
                        <div className="flex items-center gap-1 shrink-0">
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Link to={`/dashboard/fii/${ticker}`}>
                                <Button variant="ghost" size="icon" className="h-6 w-6 opacity-0 group-hover:opacity-100">
                                  <ExternalLink className="h-3 w-3" />
                                </Button>
                              </Link>
                            </TooltipTrigger>
                            <TooltipContent>Ver detalhes</TooltipContent>
                          </Tooltip>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-6 w-6 text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100"
                            onClick={() => removeTicker(activeList.id, ticker)}
                          >
                            <X className="h-3 w-3" />
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
