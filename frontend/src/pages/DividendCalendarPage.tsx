import { useState, useCallback, useEffect } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import { Download, CalendarDays, Wallet, TrendingUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  fetchDividendCalendar, fetchPortfolioIncome,
  DividendEvent, IncomeMonth,
} from "../services/api";
import { usePortfolio } from "@/hooks/use-portfolio";

// ─── helpers ─────────────────────────────────────────────────────────────────

const MONTH_NAMES = [
  "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
  "Jul", "Ago", "Set", "Out", "Nov", "Dez",
];
const MONTH_NAMES_FULL = [
  "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
  "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
];

const SECTOR_COLOR: Record<string, string> = {
  "Logística":           "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200",
  "Galpão":              "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200",
  "Lajes Corporativas":  "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200",
  "Shopping":            "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-200",
  "Shoppings":           "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-200",
  "Papel (CRI)":         "bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-200",
  "Papel (CRA)":         "bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-200",
  "CRI":                 "bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-200",
};

function sectorColor(setor: string): string {
  for (const [key, cls] of Object.entries(SECTOR_COLOR)) {
    if (setor.includes(key)) return cls;
  }
  return "bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-200";
}

function getDaysInMonth(year: number, month: number) {
  return new Date(year, month, 0).getDate();
}
function getFirstWeekday(year: number, month: number) {
  return new Date(year, month - 1, 1).getDay();
}
function today() {
  return new Date().toISOString().slice(0, 10);
}
function daysUntil(dateStr: string): number {
  const d = new Date(dateStr);
  const t = new Date(today());
  return Math.ceil((d.getTime() - t.getTime()) / 86400000);
}
function fmtBRL(v: number) {
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

// ─── Legend ──────────────────────────────────────────────────────────────────

const LEGEND = [
  { color: "bg-blue-200",   label: "Logística / Galpão" },
  { color: "bg-green-200",  label: "Lajes Corporativas" },
  { color: "bg-yellow-200", label: "Shopping" },
  { color: "bg-orange-200", label: "Papel (CRI/CRA)" },
  { color: "bg-purple-200", label: "Híbrido / Outros" },
];

// ─── EventChip ───────────────────────────────────────────────────────────────

function EventChip({ ev }: { ev: DividendEvent }) {
  const base = sectorColor(ev.setor);
  const past = ev.pay_date < today();
  const near = !past && daysUntil(ev.pay_date) <= 7;
  const est  = !ev.confirmado;
  return (
    <span
      title={`${ev.ticker} — pag. ${ev.pay_date} — R$ ${ev.valor_por_cota.toFixed(4)}`}
      className={[
        "inline-flex items-center gap-0.5 px-1 py-0.5 rounded text-[10px] font-medium leading-none",
        base,
        past ? "line-through opacity-50" : "",
        near ? "ring-1 ring-blue-400" : "",
        est  ? "opacity-70 italic" : "",
      ].join(" ")}
    >
      {est ? "~" : ""}{ev.ticker.replace(/\.SA$/, "")}
      <span className="opacity-70">R${ev.valor_por_cota.toFixed(2)}</span>
    </span>
  );
}

// ─── CalendarGrid ─────────────────────────────────────────────────────────────

function CalendarGrid({ year, month, events }: { year: number; month: number; events: DividendEvent[] }) {
  const days = getDaysInMonth(year, month);
  const startDay = getFirstWeekday(year, month);
  const byDay: Record<number, DividendEvent[]> = {};
  for (const ev of events) {
    const d = new Date(ev.pay_date);
    if (d.getFullYear() === year && d.getMonth() + 1 === month) {
      const day = d.getDate();
      if (!byDay[day]) byDay[day] = [];
      byDay[day].push(ev);
    }
  }
  const cells: (number | null)[] = [
    ...Array(startDay).fill(null),
    ...Array.from({ length: days }, (_, i) => i + 1),
  ];
  while (cells.length % 7 !== 0) cells.push(null);

  const todayStr = today();
  const todayDay = new Date(todayStr).getDate();
  const isCurrentMonth = new Date().getFullYear() === year && new Date().getMonth() + 1 === month;

  return (
    <div className="grid grid-cols-7 gap-px bg-border rounded-lg overflow-hidden text-sm">
      {["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"].map((d) => (
        <div key={d} className="bg-muted/50 text-muted-foreground text-xs font-medium text-center py-1">{d}</div>
      ))}
      {cells.map((day, idx) => {
        if (!day) return <div key={idx} className="bg-background min-h-[72px]" />;
        const evs = byDay[day] || [];
        const isToday = isCurrentMonth && day === todayDay;
        return (
          <div
            key={idx}
            className={[
              "bg-background min-h-[72px] p-1 flex flex-col gap-0.5",
              isToday ? "ring-2 ring-primary ring-inset" : "",
              evs.length > 0 ? "bg-muted/20" : "",
            ].join(" ")}
          >
            <span className={["text-xs font-mono self-end", isToday ? "text-primary font-bold" : "text-muted-foreground"].join(" ")}>
              {day}
            </span>
            {evs.map((ev, i) => <EventChip key={i} ev={ev} />)}
          </div>
        );
      })}
    </div>
  );
}

// ─── AnnualTimeline ───────────────────────────────────────────────────────────

function AnnualTimeline({ projection }: { projection: IncomeMonth[] }) {
  if (!projection.length) return null;
  const max = Math.max(...projection.map((p) => p.total_renda), 1);
  const now = new Date().toISOString().slice(0, 7); // "YYYY-MM"

  const chartData = projection.map((p) => ({
    month: MONTH_NAMES[parseInt(p.month.slice(5, 7), 10) - 1],
    renda: p.total_renda,
    isPast: p.month < now,
    isCurrent: p.month === now,
  }));

  return (
    <div className="rounded-lg border border-border bg-card p-4 space-y-3">
      <div className="flex items-center gap-2">
        <TrendingUp className="w-4 h-4 text-primary" />
        <h3 className="font-semibold text-sm">Renda projetada — 12 meses</h3>
      </div>
      <ResponsiveContainer width="100%" height={120}>
        <BarChart data={chartData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
          <XAxis dataKey="month" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fontSize: 9 }} axisLine={false} tickLine={false}
            tickFormatter={(v) => v >= 1000 ? `${(v / 1000).toFixed(1)}k` : String(v)} />
          <Tooltip
            formatter={(v: number) => [fmtBRL(v), "Renda"]}
            contentStyle={{ fontSize: 11, borderRadius: 6 }}
          />
          <Bar dataKey="renda" radius={[3, 3, 0, 0]}>
            {chartData.map((entry, i) => (
              <Cell
                key={i}
                fill={entry.isCurrent ? "hsl(var(--primary))" : entry.isPast ? "hsl(var(--muted-foreground))" : "hsl(var(--accent))"}
                opacity={entry.isPast ? 0.4 : 1}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div className="flex justify-between text-xs text-muted-foreground font-mono">
        <span>Total 12M: {fmtBRL(projection.reduce((s, p) => s + p.total_renda, 0))}</span>
        <span>Média/mês: {fmtBRL(projection.reduce((s, p) => s + p.total_renda, 0) / projection.length)}</span>
      </div>
    </div>
  );
}

// ─── Sidebar ─────────────────────────────────────────────────────────────────

function CalendarSidebar({
  events, year, month, projection,
}: {
  events: DividendEvent[];
  year: number;
  month: number;
  projection: IncomeMonth[];
}) {
  const confirmed = events.filter((e) => e.confirmado);
  const totalBRL  = confirmed.reduce((s, e) => s + e.valor_por_cota, 0);
  const uniqueFIIs = new Set(events.map((e) => e.ticker)).size;
  const avgDY = events.length ? events.reduce((s, e) => s + e.valor_por_cota, 0) / events.length : 0;

  return (
    <aside className="w-60 shrink-0 flex flex-col gap-4">
      <div className="rounded-lg border border-border bg-card p-4 space-y-3">
        <h3 className="font-semibold text-sm">📅 {MONTH_NAMES_FULL[month - 1]} {year}</h3>
        <div className="space-y-1 text-sm">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Total (confirmado)</span>
            <span className="font-mono font-medium">{fmtBRL(totalBRL)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">FIIs pagando</span>
            <span className="font-mono font-medium">{uniqueFIIs}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Média / cota</span>
            <span className="font-mono font-medium">{fmtBRL(avgDY)}</span>
          </div>
        </div>
      </div>

      {projection.length > 0 && <AnnualTimeline projection={projection} />}

      <div className="rounded-lg border border-border bg-card p-4 space-y-2">
        <h3 className="font-semibold text-xs text-muted-foreground uppercase tracking-wide">Legenda</h3>
        {LEGEND.map((l) => (
          <div key={l.label} className="flex items-center gap-2 text-xs">
            <span className={`w-3 h-3 rounded-sm ${l.color}`} />
            <span>{l.label}</span>
          </div>
        ))}
        <div className="flex items-center gap-2 text-xs">
          <span className="w-3 h-3 rounded-sm bg-gray-200 opacity-70" />
          <span className="italic">Estimativa futura</span>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span className="w-3 h-3 rounded-sm bg-background ring-1 ring-blue-400" />
          <span>Próximo (≤7 dias)</span>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span className="w-3 h-3 rounded-sm bg-background opacity-50 text-[8px]">X</span>
          <span className="line-through opacity-60">Já pago</span>
        </div>
      </div>

      {events.length > 0 && (
        <div className="rounded-lg border border-border bg-card p-4 space-y-2">
          <h3 className="font-semibold text-xs text-muted-foreground uppercase tracking-wide">Eventos</h3>
          <div className="space-y-1 max-h-64 overflow-y-auto">
            {events.map((ev, i) => (
              <div key={i} className="flex justify-between text-xs py-0.5 border-b border-border/30 last:border-0">
                <span className="font-medium">{ev.ticker.replace(/\.SA$/, "")}</span>
                <span className="text-muted-foreground">{ev.pay_date.slice(5)}</span>
                <span className="font-mono">{fmtBRL(ev.valor_por_cota)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </aside>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function DividendCalendarPage() {
  const now = new Date();
  const [year, setYear]     = useState(now.getFullYear());
  const [month, setMonth]   = useState(now.getMonth() + 1);
  const [events, setEvents]   = useState<DividendEvent[]>([]);
  const [projection, setProjection] = useState<IncomeMonth[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);
  const [loaded, setLoaded]   = useState(false);
  const [onlyPortfolio, setOnlyPortfolio] = useState(false);

  const { portfolio, quantities, isEmpty } = usePortfolio();
  const portfolioTickers = portfolio.assets.map((a) => a.ticker);

  const load = useCallback(async (y: number, m: number, filterPortfolio: boolean) => {
    setLoading(true);
    setError(null);
    try {
      const tickerParam = filterPortfolio && portfolioTickers.length > 0
        ? portfolioTickers.join(",")
        : undefined;

      const data = await fetchDividendCalendar(y, m, tickerParam);
      setEvents(data.events);
      setLoaded(true);

      // Load annual projection if portfolio filter active and user has holdings
      if (filterPortfolio && portfolioTickers.length > 0 && Object.keys(quantities).length > 0) {
        const inc = await fetchPortfolioIncome(quantities, 12);
        setProjection(inc.projection);
      } else {
        setProjection([]);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erro ao carregar calendário");
    } finally {
      setLoading(false);
    }
  }, [portfolioTickers, quantities]);

  useEffect(() => {
    if (!loaded && !loading && !error) {
      load(year, month, onlyPortfolio);
    }
  }, [loaded, loading, error, year, month, onlyPortfolio, load]);

  const prevMonth = useCallback(() => {
    const m = month === 1 ? 12 : month - 1;
    const y = month === 1 ? year - 1 : year;
    setYear(y); setMonth(m); load(y, m, onlyPortfolio);
  }, [year, month, load, onlyPortfolio]);

  const nextMonth = useCallback(() => {
    const m = month === 12 ? 1 : month + 1;
    const y = month === 12 ? year + 1 : year;
    setYear(y); setMonth(m); load(y, m, onlyPortfolio);
  }, [year, month, load, onlyPortfolio]);

  const togglePortfolioFilter = useCallback(() => {
    const next = !onlyPortfolio;
    setOnlyPortfolio(next);
    load(year, month, next);
  }, [onlyPortfolio, year, month, load]);

  // ── Export CSV ──────────────────────────────────────────────────────────────
  const exportCSV = useCallback(() => {
    const headers = ["Ticker", "Setor", "Ex-Date", "Pay-Date", "Valor/Cota", "Tipo", "Confirmado"];
    const rows = events.map((ev) => [
      ev.ticker.replace(/\.SA$/, ""),
      ev.setor,
      ev.ex_date,
      ev.pay_date,
      ev.valor_por_cota.toFixed(4),
      ev.tipo,
      ev.confirmado ? "Sim" : "Estimado",
    ]);
    const csv = [headers.join(";"), ...rows.map((r) => r.join(";"))].join("\n");
    const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `dividendos_${year}_${String(month).padStart(2, "0")}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [events, year, month]);

  // ── Export ICS (Google Calendar) ────────────────────────────────────────────
  const exportICS = useCallback(() => {
    const lines = [
      "BEGIN:VCALENDAR",
      "VERSION:2.0",
      "PRODID:-//AlphaCota//Dividendos//PT",
      "CALSCALE:GREGORIAN",
      "METHOD:PUBLISH",
    ];
    for (const ev of events) {
      const payDateClean = ev.pay_date.replace(/-/g, "");
      const exDateClean  = ev.ex_date.replace(/-/g, "");
      const uid = `${ev.ticker}-${ev.pay_date}@alphacota`;
      lines.push(
        "BEGIN:VEVENT",
        `UID:${uid}`,
        `DTSTART;VALUE=DATE:${payDateClean}`,
        `DTEND;VALUE=DATE:${payDateClean}`,
        `SUMMARY:${ev.ticker.replace(/\.SA$/, "")} — R$ ${ev.valor_por_cota.toFixed(4)}/cota`,
        `DESCRIPTION:Pagamento de dividendo\\nValor: R$ ${ev.valor_por_cota.toFixed(4)}/cota\\nEx-date: ${ev.ex_date}\\nFonte: ${ev.fonte}`,
        `CATEGORIES:Dividendos,FII`,
        `TRANSP:TRANSPARENT`,
        "END:VEVENT",
      );
    }
    lines.push("END:VCALENDAR");
    const ics = lines.join("\r\n");
    const blob = new Blob([ics], { type: "text/calendar;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `dividendos_${year}_${String(month).padStart(2, "0")}.ics`;
    a.click();
    URL.revokeObjectURL(url);
  }, [events, year, month]);

  return (
    <div className="p-6 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2">
            <CalendarDays className="w-5 h-5 text-primary" />
            Calendário de Dividendos
          </h1>
          <p className="text-sm text-muted-foreground">Datas de pagamento e valores por cota</p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {/* Portfolio filter */}
          <Button
            variant={onlyPortfolio ? "default" : "outline"}
            size="sm"
            onClick={togglePortfolioFilter}
            disabled={isEmpty}
            title={isEmpty ? "Adicione FIIs à sua carteira primeiro" : "Filtrar pela minha carteira"}
            className={onlyPortfolio ? "" : "border-border/50 hover:bg-secondary"}
          >
            <Wallet className="w-4 h-4 mr-1.5" />
            Minha Carteira
          </Button>

          {/* Export buttons */}
          {events.length > 0 && (
            <>
              <Button variant="outline" size="sm" onClick={exportCSV} className="border-border/50 hover:bg-secondary gap-1.5">
                <Download className="w-3.5 h-3.5" />
                CSV
              </Button>
              <Button variant="outline" size="sm" onClick={exportICS} className="border-border/50 hover:bg-secondary gap-1.5">
                <Download className="w-3.5 h-3.5" />
                .ICS
              </Button>
            </>
          )}

          {/* Month navigation */}
          <div className="flex items-center gap-1">
            <button
              onClick={prevMonth}
              className="px-3 py-1.5 rounded-md border border-border text-sm hover:bg-muted transition-colors"
            >
              ←
            </button>
            <span className="px-3 py-1.5 font-medium text-sm min-w-[130px] text-center">
              {MONTH_NAMES_FULL[month - 1]} {year}
            </span>
            <button
              onClick={nextMonth}
              className="px-3 py-1.5 rounded-md border border-border text-sm hover:bg-muted transition-colors"
            >
              →
            </button>
          </div>
        </div>
      </div>

      {onlyPortfolio && !isEmpty && (
        <div className="text-xs text-muted-foreground bg-primary/5 border border-primary/20 rounded-lg px-3 py-2">
          Mostrando apenas os {portfolioTickers.length} FIIs da sua carteira.
        </div>
      )}

      {/* Body */}
      {loading && (
        <div className="flex items-center justify-center h-64 text-muted-foreground text-sm">
          Carregando calendário...
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
          <button onClick={() => load(year, month, onlyPortfolio)} className="ml-2 underline">
            Tentar novamente
          </button>
        </div>
      )}

      {!loading && !error && (
        <div className="flex gap-4 items-start">
          <div className="flex-1 min-w-0">
            <CalendarGrid year={year} month={month} events={events} />
            {events.length === 0 && (
              <p className="text-center text-muted-foreground text-sm mt-8">
                Nenhum evento de dividendo encontrado para {MONTH_NAMES_FULL[month - 1]} {year}.
                {onlyPortfolio && " Tente desativar o filtro de carteira."}
              </p>
            )}
          </div>
          <CalendarSidebar events={events} year={year} month={month} projection={projection} />
        </div>
      )}
    </div>
  );
}
