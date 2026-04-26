"use client";

/**
 * Route-level error boundary. Next.js App Router renders this when a
 * descendant Server or Client Component throws during render. We surface
 * the message via the existing `<ErrorState />` plus a "Reload page"
 * button — the `reset()` callback Next provides re-renders the route
 * tree, which works for transient failures (e.g. a stale React Query
 * cache); a hard reload is the fallback for everything else.
 */
import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/common/ErrorState";

type Props = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function RouteError({ error, reset }: Props) {
  useEffect(() => {
    // eslint-disable-next-line no-console
    console.error("[route error]", error);
  }, [error]);

  return (
    <div className="mx-auto w-full max-w-3xl space-y-3 p-6">
      <ErrorState
        message={error.message || "Something went wrong rendering this page."}
        retry={reset}
      />
      <div className="flex gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => {
            if (typeof window !== "undefined") window.location.reload();
          }}
        >
          Reload page
        </Button>
      </div>
    </div>
  );
}
