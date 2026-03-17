import { motion } from "framer-motion";
import { Radar, Calculator, Briefcase, Bot, LineChart } from "lucide-react";

const features = [
  {
    icon: Radar,
    title: "Market Scanner",
    description: "Varredura automática de todos os FIIs da B3. Coleta, normaliza e estrutura indicadores fundamentalistas em tempo real.",
    tag: "DADOS",
  },
  {
    icon: Calculator,
    title: "Quantitative Engines",
    description: "Motores de valuation, scoring de qualidade, análise de risco e detecção de oportunidades baseados em modelos quantitativos.",
    tag: "ANÁLISE",
  },
  {
    icon: Briefcase,
    title: "Portfolio Intelligence",
    description: "Análise de diversificação, detecção de concentração excessiva e recomendações de rebalanceamento personalizado.",
    tag: "CARTEIRA",
  },
  {
    icon: Bot,
    title: "AI Insight Layer",
    description: "Interpretação de notícias, geração de insights contextuais e explicação de recomendações via IA com cache inteligente.",
    tag: "IA",
  },
  {
    icon: LineChart,
    title: "Financial Projections",
    description: "Simulador de renda passiva, projeção de reinvestimento e estimativa de tempo para independência financeira.",
    tag: "PROJEÇÃO",
  },
];

const FeaturesSection = () => {
  return (
    <section className="relative py-24 overflow-hidden">
      <div className="container px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-center mb-16"
        >
          <span className="font-mono text-sm text-primary tracking-widest uppercase">Módulos</span>
          <h2 className="text-4xl md:text-5xl font-bold mt-3 mb-4">
            Arquitetura <span className="text-gradient-primary">modular</span>
          </h2>
          <p className="text-muted-foreground max-w-lg mx-auto">
            Cinco módulos especializados que trabalham em conjunto para gerar recomendações financeiras de alta qualidade.
          </p>
        </motion.div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {features.map((feature, i) => (
            <motion.div
              key={feature.title}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.1 }}
              className="glass-card p-6 group hover:border-primary/30 transition-all duration-300"
            >
              <div className="flex items-center justify-between mb-4">
                <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center group-hover:bg-primary/20 transition-colors">
                  <feature.icon className="w-5 h-5 text-primary" />
                </div>
                <span className="font-mono text-[10px] tracking-widest text-muted-foreground bg-secondary px-2 py-1 rounded">
                  {feature.tag}
                </span>
              </div>
              <h3 className="text-lg font-semibold mb-2">{feature.title}</h3>
              <p className="text-sm text-muted-foreground leading-relaxed">{feature.description}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default FeaturesSection;
