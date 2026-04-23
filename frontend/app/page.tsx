import { EmptyState } from "@/components/common/EmptyState";

/**
 * Home page. Phase 4 replaces these placeholders with the hero card
 * and ticker tape. Today this is an EmptyState that proves the
 * theme tokens + Nav + Footer all wire up.
 */
export default function HomePage() {
  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-6 lg:py-10 space-y-6">
      {/* Ticker placeholder — Phase 5 lands the real strip */}
      <section
        aria-label="Live quotes"
        className="h-10 rounded-md border border-border bg-bg-2 flex items-center px-4 text-xs text-text-secondary"
      >
        Ticker tape · Phase 5
      </section>

      {/* Hero placeholder — Phase 4 lands the real hero card */}
      <section
        aria-label="Trade idea"
        className="rounded-lg border border-border bg-bg-2 p-6"
      >
        <EmptyState
          title="Trade idea will appear here"
          message="Phase 4 wires this to /api/thesis/latest."
        />
      </section>
    </div>
  );
}
