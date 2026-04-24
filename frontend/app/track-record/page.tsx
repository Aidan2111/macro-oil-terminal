import { Section } from "@/components/common/Section";
import { LoadingSkeleton } from "@/components/common/LoadingSkeleton";

export default function TrackRecordPage() {
  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-2">
      <Section
        id="track-record"
        title="Track Record"
        subtitle="Backtest outcomes, hit rate, Sharpe, drawdown."
      >
        <LoadingSkeleton lines={6} height="h-5" />
      </Section>
    </div>
  );
}
