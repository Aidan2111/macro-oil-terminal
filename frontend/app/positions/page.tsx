import { Section } from "@/components/common/Section";
import { PositionsPanel } from "@/components/positions/PositionsPanel";

// The panel has an always-live SSE subscription and a server-side
// initial fetch — opt out of Next's full-route cache so each request
// gets a fresh snapshot.
export const dynamic = "force-dynamic";

export default function PositionsPage() {
  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-2">
      <Section
        id="positions"
        title="Positions"
        subtitle="Open trades, realised/unrealised PnL, account equity."
      >
        <PositionsPanel />
      </Section>
    </div>
  );
}
