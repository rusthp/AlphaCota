import { motion } from "framer-motion";

const mockFIIs = [
  { ticker: "HGLG11", score: 92, dy: "8.2%", pvp: "0.95", change: "+1.4%" },
  { ticker: "XPML11", score: 88, dy: "7.8%", pvp: "0.91", change: "+0.8%" },
  { ticker: "MXRF11", score: 85, dy: "11.2%", pvp: "1.02", change: "-0.3%" },
  { ticker: "VISC11", score: 83, dy: "8.5%", pvp: "0.88", change: "+2.1%" },
  { ticker: "KNRI11", score: 81, dy: "7.1%", pvp: "0.93", change: "+0.5%" },
];

const DashboardPreview = () => {
  return (
    <section className="relative py-24 overflow-hidden">
      <div className="absolute inset-0 bg-grid-pattern opacity-10" />
      <div className="container px-6 relative z-10">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-center mb-12"
        >
          <span className="font-mono text-sm text-primary tracking-widest uppercase">Preview</span>
          <h2 className="text-4xl md:text-5xl font-bold mt-3 mb-4">
            Dados em <span className="text-gradient-primary">tempo real</span>
          </h2>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.2 }}
          className="glass-card glow-primary max-w-4xl mx-auto overflow-hidden"
        >
          {/* Header bar */}
          <div className="flex items-center gap-2 px-6 py-3 border-b border-border/50 bg-secondary/30">
            <div className="w-3 h-3 rounded-full bg-destructive/60" />
            <div className="w-3 h-3 rounded-full bg-accent/40" />
            <div className="w-3 h-3 rounded-full bg-primary/40" />
            <span className="ml-4 font-mono text-xs text-muted-foreground">alphacota/scanner — Top FIIs por Score</span>
          </div>

          {/* Table */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border/30">
                  <th className="text-left px-6 py-3 font-mono text-xs text-muted-foreground font-medium">TICKER</th>
                  <th className="text-center px-6 py-3 font-mono text-xs text-muted-foreground font-medium">SCORE</th>
                  <th className="text-center px-6 py-3 font-mono text-xs text-muted-foreground font-medium">DY</th>
                  <th className="text-center px-6 py-3 font-mono text-xs text-muted-foreground font-medium">P/VP</th>
                  <th className="text-right px-6 py-3 font-mono text-xs text-muted-foreground font-medium">VAR</th>
                </tr>
              </thead>
              <tbody>
                {mockFIIs.map((fii, i) => (
                  <motion.tr
                    key={fii.ticker}
                    initial={{ opacity: 0, x: -10 }}
                    whileInView={{ opacity: 1, x: 0 }}
                    viewport={{ once: true }}
                    transition={{ delay: 0.3 + i * 0.08 }}
                    className="border-b border-border/20 hover:bg-secondary/20 transition-colors"
                  >
                    <td className="px-6 py-4 font-mono font-semibold text-foreground">{fii.ticker}</td>
                    <td className="px-6 py-4 text-center">
                      <span className="inline-flex items-center justify-center w-10 h-6 rounded bg-primary/15 text-primary font-mono font-bold text-xs">
                        {fii.score}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-center font-mono text-accent">{fii.dy}</td>
                    <td className="px-6 py-4 text-center font-mono text-muted-foreground">{fii.pvp}</td>
                    <td className={`px-6 py-4 text-right font-mono font-medium ${fii.change.startsWith('+') ? 'text-accent' : 'text-destructive'}`}>
                      {fii.change}
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
        </motion.div>
      </div>
    </section>
  );
};

export default DashboardPreview;
