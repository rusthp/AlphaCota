import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Component, ReactNode } from "react";
import Index from "./pages/Index";
import LoginPage from "./pages/LoginPage";
import RequireAuth from "./components/RequireAuth";
import NotFound from "./pages/NotFound";
import DashboardLayout from "./components/DashboardLayout";
import ScannerPage from "./pages/ScannerPage";
import SimulatorPage from "./pages/SimulatorPage";
import PortfolioPage from "./pages/PortfolioPage";
import FIIDetailPage from "./pages/FIIDetailPage";
import AIInsightsPage from "./pages/AIInsightsPage";
import MacroPage from "./pages/MacroPage";
import MomentumPage from "./pages/MomentumPage";
import StressPage from "./pages/StressPage";
import CorrelationPage from "./pages/CorrelationPage";
import ClustersPage from "./pages/ClustersPage";
import DividendCalendarPage from "./pages/DividendCalendarPage";
import ComparePage from "./pages/ComparePage";
import WatchlistPage from "./pages/WatchlistPage";
import PolymarketPage from "./pages/PolymarketPage";
import TerminalPage from "./pages/TerminalPage";

class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  render() {
    if (this.state.error) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-background text-foreground p-8">
          <div className="text-center space-y-3">
            <p className="text-destructive font-semibold text-lg">Erro inesperado</p>
            <p className="text-muted-foreground text-sm font-mono">{(this.state.error as Error).message}</p>
            <button className="text-xs underline text-muted-foreground" onClick={() => this.setState({ error: null })}>
              Tentar novamente
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

const queryClient = new QueryClient();

const App = () => (
  <ErrorBoundary>
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Index />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/dashboard" element={<RequireAuth><DashboardLayout /></RequireAuth>}>
            <Route index element={<Navigate to="scanner" replace />} />
            <Route path="scanner" element={<ScannerPage />} />
            <Route path="fii/:ticker" element={<FIIDetailPage />} />
            <Route path="portfolio" element={<PortfolioPage />} />
            <Route path="simulator" element={<SimulatorPage />} />
            <Route path="ai-insights" element={<AIInsightsPage />} />
            <Route path="macro" element={<MacroPage />} />
            <Route path="momentum" element={<MomentumPage />} />
            <Route path="stress" element={<StressPage />} />
            <Route path="correlation" element={<CorrelationPage />} />
            <Route path="clusters" element={<ClustersPage />} />
            <Route path="calendar" element={<DividendCalendarPage />} />
            <Route path="compare" element={<ComparePage />} />
            <Route path="watchlist" element={<WatchlistPage />} />
            <Route path="polymarket" element={<PolymarketPage />} />
            <Route path="terminal" element={<TerminalPage />} />
          </Route>
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
  </ErrorBoundary>
);

export default App;
