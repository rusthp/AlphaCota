import Navbar from "@/components/Navbar";
import HeroSection from "@/components/HeroSection";
import FeaturesSection from "@/components/FeaturesSection";
import DashboardPreview from "@/components/DashboardPreview";
import ProfilesSection from "@/components/ProfilesSection";
import CTASection from "@/components/CTASection";
import Footer from "@/components/Footer";

const Index = () => {
  return (
    <div className="min-h-screen bg-gradient-dark">
      <Navbar />
      <HeroSection />
      <div id="features">
        <FeaturesSection />
      </div>
      <div id="preview">
        <DashboardPreview />
      </div>
      <div id="profiles">
        <ProfilesSection />
      </div>
      <CTASection />
      <Footer />
    </div>
  );
};

export default Index;
