import dynamic from "next/dynamic";
import { Section } from "@/components/common/Section";
import { ChartShimmer } from "@/components/illustrations/ChartShimmer";
import { TradeIdeaHero } from "@/components/hero/TradeIdeaHero";

/**
 * `DataQualityTile` is a client component that polls /api/data-quality
 * every 60 s. We dynamic-import with `ssr: false` so the tile JS isn't
 * on the LCP critical path — Lighthouse keeps the hero card as the
 * LCP candidate and the tile fades in client-side once below-the-fold.
 */
const DataQualityTile = dynamic(
  () =>
    import("@/components/data-quality/DataQualityTile").then(
      (m) => m.DataQualityTile,
    ),
  { ssr: false },
);

/**
 * Home page shell. Wave 2 Sub-F ships the real `TradeIdeaHero`; the
 * ticker placeholder below is filled by Sub-G. Q1 data-quality slice
 * adds a lazy-mounted DataQualityTile under the hero.
 */
export default function HomePage() {
  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-2">
      <h1 className="sr-only">Macro Oil Terminal &mdash; today&rsquo;s read</h1>
      <Section
        id="home"
        title="Today&rsquo;s read"
        subtitle="Live stance and trade idea on the Brent-WTI spread."
      >
        <TradeIdeaHero />
      </Section>
      <Section
        id="data-quality"
        title="Data quality"
        subtitle="Per-provider sanity at a glance &mdash; hover for last-good and observation count."
      >
        {/* Q1-DATA-QUALITY-TILE */}
        <DataQualityTile />
      </Section>
      <Section
        id="ticker"
        title="Market ticker"
        subtitle="Live Brent, WTI, spread, and inventory &mdash; updated as quotes arrive."
      >
        <ChartShimmer height={120} bars={16} />
      </Section>
    </div>
  );
}
