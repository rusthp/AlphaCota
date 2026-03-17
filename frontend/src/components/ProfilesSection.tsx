import { motion } from "framer-motion";
import { User, TrendingUp, Zap, BookOpen } from "lucide-react";

const profiles = [
  {
    icon: User,
    name: "Iniciante",
    description: "Foco em segurança e aprendizado. Ativos de baixa volatilidade e alta previsibilidade de renda.",
    risk: "Baixo",
    focus: "Renda",
    color: "text-primary",
  },
  {
    icon: TrendingUp,
    name: "Moderado",
    description: "Equilíbrio entre renda e valorização. Diversificação ampla com exposição controlada a risco.",
    risk: "Médio",
    focus: "Renda + Crescimento",
    color: "text-accent",
  },
  {
    icon: Zap,
    name: "Agressivo",
    description: "Busca máxima valorização e yield. Maior tolerância a volatilidade e concentração setorial.",
    risk: "Alto",
    focus: "Crescimento",
    color: "text-destructive",
  },
  {
    icon: BookOpen,
    name: "Graham",
    description: "Estilo fundamentalista clássico. Margem de segurança, valor patrimonial e consistência de dividendos.",
    risk: "Baixo-Médio",
    focus: "Valor",
    color: "text-primary",
  },
];

const ProfilesSection = () => {
  return (
    <section className="relative py-24">
      <div className="container px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-center mb-16"
        >
          <span className="font-mono text-sm text-primary tracking-widest uppercase">Perfis</span>
          <h2 className="text-4xl md:text-5xl font-bold mt-3 mb-4">
            Adaptado ao seu <span className="text-gradient-primary">estilo</span>
          </h2>
          <p className="text-muted-foreground max-w-lg mx-auto">
            Recomendações personalizadas de acordo com sua tolerância a risco e objetivos de investimento.
          </p>
        </motion.div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 max-w-5xl mx-auto">
          {profiles.map((profile, i) => (
            <motion.div
              key={profile.name}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.1 }}
              className="glass-card p-6 text-center group hover:border-primary/30 transition-all duration-300"
            >
              <div className="w-12 h-12 rounded-full bg-secondary flex items-center justify-center mx-auto mb-4 group-hover:scale-110 transition-transform">
                <profile.icon className={`w-5 h-5 ${profile.color}`} />
              </div>
              <h3 className="font-semibold text-lg mb-2">{profile.name}</h3>
              <p className="text-sm text-muted-foreground mb-4 leading-relaxed">{profile.description}</p>
              <div className="flex justify-between text-xs font-mono">
                <span className="text-muted-foreground">Risco: <span className="text-foreground">{profile.risk}</span></span>
                <span className="text-muted-foreground">Foco: <span className="text-foreground">{profile.focus}</span></span>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default ProfilesSection;
