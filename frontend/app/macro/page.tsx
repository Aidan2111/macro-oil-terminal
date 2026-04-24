import { Section } from "@/components/common/Section";
import { LoadingSkeleton } from "@/components/common/LoadingSkeleton";

export default function MacroPage() {
  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-2">
      <Section
        id="macro"
        title="Macro"
        subtitle="Crude spreads, inventory deltas, CFTC positioning."
      >
        <LoadingSkeleton lines={6} height="h-5" />
      </Section>
    </div>
  );
}
