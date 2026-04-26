import { Section } from "@/components/common/Section";
import { TrackRecord } from "@/components/track-record/TrackRecord";

// Track Record is publicly visible — no auth. Component is client-only
// so static export bakes a single HTML shell that hydrates with data.

export default function TrackRecordPage() {
  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-2">
      <Section
        id="track-record"
        title="Track Record"
        subtitle="How the model has performed — hit rate, returns, drawdowns."
      >
        <TrackRecord />
      </Section>
    </div>
  );
}
