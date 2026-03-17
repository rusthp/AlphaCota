const Footer = () => {
  return (
    <footer className="border-t border-border/30 py-8">
      <div className="container px-6 flex flex-col md:flex-row items-center justify-between gap-4 text-sm text-muted-foreground">
        <div className="flex items-center gap-2">
          <span className="font-bold text-foreground">AlphaCota</span>
          <span>· Inteligência Financeira para FIIs</span>
        </div>
        <span className="font-mono text-xs">© 2026 AlphaCota. Todos os direitos reservados.</span>
      </div>
    </footer>
  );
};

export default Footer;
