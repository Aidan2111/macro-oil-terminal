import { Section } from "@/components/common/Section";
import { LoadingSkeleton } from "@/components/common/LoadingSkeleton";

export default function PositionsPage() {
  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-2">
      <Section
        id="positions"
        title="Positions"
        subtitle="Open trades, realised/unrealised PnL, account equity."
      >
        <LoadingSkeleton lines={4} height="h-6" />
      </Section>
    </div>
  );
}
