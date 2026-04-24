import { Section } from "@/components/common/Section";
import { LoadingSkeleton } from "@/components/common/LoadingSkeleton";

/**
 * Home page shell — Wave 2 wires the real hero + ticker tape. For
 * now the page proves the layout tokens + providers all boot.
 */
export default function HomePage() {
  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-2">
      <Section
        id="home"
        title="Today's dislocation"
        subtitle="Trade idea, spread chart, and supporting inventory data will land here in Wave 2."
      >
        <LoadingSkeleton lines={4} height="h-6" />
      </Section>
    </div>
  );
}
