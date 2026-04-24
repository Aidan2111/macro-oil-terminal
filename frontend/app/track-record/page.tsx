import { Section } from "@/components/common/Section";
import { TrackRecord } from "@/components/track-record/TrackRecord";

// Track Record is publicly visible — no auth. The component
// fetches on the client so the bundle stays small and we don't
// need to proxy the history endpoint during SSR.
export const dynamic = "force-dynamic";

export default function TrackRecordPage() {
  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-2">
      <Section
        id="track-record"
        title="Track Record"
        subtitle="Backtest outcomes, hit rate, Sharpe, drawdown."
      >
        <TrackRecord />
      </Section>
    </div>
  );
}
