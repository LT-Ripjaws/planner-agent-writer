import { AgentStory } from "@/components/landing/agent-story";
import { Hero } from "@/components/landing/hero";
import { HowItWorks } from "@/components/landing/how-it-works";
import { ScrollProgress } from "@/components/landing/scroll-progress";
import { Showcase } from "@/components/landing/showcase";
import { SiteFooter } from "@/components/landing/site-footer";
import { SiteHeader } from "@/components/landing/site-header";

export default function HomePage() {
  return (
    <>
      <ScrollProgress />
      <SiteHeader />
      <main className="overflow-hidden">
        <Hero />

        <div className="relative overflow-hidden">
          <HowItWorks />
        </div>

        <AgentStory />

        <div className="relative overflow-hidden">
          <Showcase />
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
