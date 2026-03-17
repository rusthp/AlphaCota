import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Index from "./pages/Index";
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

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Index />} />
          <Route path="/dashboard" element={<DashboardLayout />}>
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
          </Route>
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
