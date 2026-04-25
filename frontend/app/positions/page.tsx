import { Section } from "@/components/common/Section";
import { PositionsPanel } from "@/components/positions/PositionsPanel";

// Static-export friendly: PositionsPanel is a client component that
// fetches at runtime via NEXT_PUBLIC_API_URL. No SSR needed.

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
