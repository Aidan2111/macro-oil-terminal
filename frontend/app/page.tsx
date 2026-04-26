import { Section } from "@/components/common/Section";
import { ChartShimmer } from "@/components/illustrations/ChartShimmer";
import { TradeIdeaHero } from "@/components/hero/TradeIdeaHero";

/**
 * Home page shell. Wave 2 Sub-F ships the real `TradeIdeaHero`; the
 * ticker placeholder below is filled by Sub-G.
 */
export default function HomePage() {
  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-2">
      <h1 className="sr-only">Macro Oil Terminal — today&rsquo;s read</h1>
      <Section
        id="home"
        title="Today&rsquo;s read"
        subtitle="Live stance and trade idea on the Brent-WTI spread."
      >
        <TradeIdeaHero />
      </Section>
      <Section
        id="ticker"
        title="Market ticker"
        subtitle="Live Brent, WTI, spread, and inventory — updated as quotes arrive."
      >
        <ChartShimmer height={120} bars={16} />
      </Section>
    </div>
  );
}
