import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";

const Navbar = () => {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 border-b border-border/30 bg-background/80 backdrop-blur-xl">
      <div className="container px-6 flex items-center justify-between h-16">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-primary/20 flex items-center justify-center">
            <span className="font-bold text-primary text-sm">α</span>
          </div>
          <span className="font-bold text-lg tracking-tight">AlphaCota</span>
        </div>
        <div className="hidden md:flex items-center gap-8 text-sm text-muted-foreground">
          <a href="#features" className="hover:text-foreground transition-colors">Módulos</a>
          <a href="#profiles" className="hover:text-foreground transition-colors">Perfis</a>
          <a href="#preview" className="hover:text-foreground transition-colors">Preview</a>
        </div>
        <Button asChild size="sm" className="font-semibold">
          <Link to="/dashboard">Acessar</Link>
        </Button>
      </div>
    </nav>
  );
};

export default Navbar;
