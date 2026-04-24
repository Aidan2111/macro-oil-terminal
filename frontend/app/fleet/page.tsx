import { Section } from "@/components/common/Section";
import { LoadingSkeleton } from "@/components/common/LoadingSkeleton";

export default function FleetPage() {
  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-2">
      <Section
        id="fleet"
        title="Fleet"
        subtitle="VLCC / Suezmax / Aframax vessels tracked in real time."
      >
        <LoadingSkeleton lines={5} height="h-5" />
      </Section>
    </div>
  );
}
