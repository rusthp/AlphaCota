import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";

const CTASection = () => {
  return (
    <section className="relative py-24">
      <div className="absolute inset-0 bg-gradient-to-t from-primary/5 to-transparent" />
      <div className="container px-6 relative z-10">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="glass-card glow-primary max-w-3xl mx-auto text-center p-12 md:p-16"
        >
          <h2 className="text-3xl md:text-4xl font-bold mb-4">
            Pronto para investir com <span className="text-gradient-primary">inteligência</span>?
          </h2>
          <p className="text-muted-foreground mb-8 max-w-md mx-auto">
            Transforme dados complexos em decisões estratégicas. Comece a construir sua carteira de FIIs com análise quantitativa.
          </p>
          <Button asChild size="lg" className="glow-primary text-lg px-8 py-6 font-semibold group">
            <Link to="/dashboard">
              Acessar AlphaCota
              <ArrowRight className="ml-2 w-5 h-5 group-hover:translate-x-1 transition-transform" />
            </Link>
          </Button>
        </motion.div>
      </div>
    </section>
  );
};

export default CTASection;
