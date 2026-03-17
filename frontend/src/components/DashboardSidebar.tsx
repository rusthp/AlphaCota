import { Radar, LineChart, Briefcase, Sparkles, ArrowLeft, Globe, TrendingUp, Shield, GitBranch, Layers } from "lucide-react";
import { NavLink } from "@/components/NavLink";
import { useLocation, Link } from "react-router-dom";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar";

const items = [
  { title: "Scanner", url: "/dashboard/scanner", icon: Radar },
  { title: "Minha Carteira", url: "/dashboard/portfolio", icon: Briefcase },
  { title: "Simulador", url: "/dashboard/simulator", icon: LineChart },
  { title: "Macro", url: "/dashboard/macro", icon: Globe },
  { title: "Momentum", url: "/dashboard/momentum", icon: TrendingUp },
  { title: "Stress Test", url: "/dashboard/stress", icon: Shield },
  { title: "Correlação", url: "/dashboard/correlation", icon: GitBranch },
  { title: "Clusters", url: "/dashboard/clusters", icon: Layers },
  { title: "AI Insights", url: "/dashboard/ai-insights", icon: Sparkles },
];

export function DashboardSidebar() {
  const { state } = useSidebar();
  const collapsed = state === "collapsed";
  const location = useLocation();
  const isExpanded = items.some((i) => location.pathname === i.url);

  return (
    <Sidebar collapsible="icon" className="border-r border-border/30">
      <SidebarContent>
        {/* Logo */}
        <div className={`flex items-center gap-2 px-4 py-4 ${collapsed ? "justify-center" : ""}`}>
          <div className="w-8 h-8 rounded-lg bg-primary/20 flex items-center justify-center flex-shrink-0">
            <span className="font-bold text-primary text-sm">α</span>
          </div>
          {!collapsed && <span className="font-bold text-lg tracking-tight">AlphaCota</span>}
        </div>

        <SidebarGroup>
          <SidebarGroupLabel className="font-mono text-[10px] tracking-widest">MÓDULOS</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {items.map((item) => (
                <SidebarMenuItem key={item.title}>
                  <SidebarMenuButton asChild>
                    <NavLink to={item.url} end className="hover:bg-secondary/50" activeClassName="bg-primary/10 text-primary font-medium">
                      <item.icon className="mr-2 h-4 w-4" />
                      {!collapsed && <span>{item.title}</span>}
                    </NavLink>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {/* Back to landing */}
        <div className="mt-auto p-4">
          <Link to="/" className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors">
            <ArrowLeft className="w-3.5 h-3.5" />
            {!collapsed && <span>Voltar ao site</span>}
          </Link>
        </div>
      </SidebarContent>
    </Sidebar>
  );
}
