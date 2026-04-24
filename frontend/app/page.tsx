import { Section } from "@/components/common/Section";
import { LoadingSkeleton } from "@/components/common/LoadingSkeleton";
import { TradeIdeaHero } from "@/components/hero/TradeIdeaHero";

/**
 * Home page shell. Wave 2 Sub-F ships the real `TradeIdeaHero`; the
 * ticker placeholder below is filled by Sub-G.
 */
export default function HomePage() {
  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-2">
      <Section
        id="home"
        title="Today's dislocation"
        subtitle="Live trade idea, stance, and executable tiers."
      >
        <TradeIdeaHero />
      </Section>
      <Section
        id="ticker"
        title="Market ticker"
        subtitle="Rolling quotes and session headlines land here in Wave 2."
      >
        <LoadingSkeleton lines={3} height="h-6" />
      </Section>
    </div>
  );
}
