"use client";

import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";

type Props = {
  message: string;
  retry?: () => void;
};

/**
 * Red-tinted card for a handled error. Renders the message + an
 * optional "Retry" button. Used by pages wrapping React Query
 * failures.
 */
export function ErrorState({ message, retry }: Props) {
  return (
    <div
      role="alert"
      className="rounded-card border border-alert/40 bg-alert/10 p-4 text-sm text-text-primary"
    >
      <div className="flex items-start gap-3">
        <AlertTriangle className="h-5 w-5 text-alert shrink-0" aria-hidden />
        <div className="flex-1 space-y-2">
          <div>{message}</div>
          {retry ? (
            <Button type="button" variant="outline" size="sm" onClick={retry}>
              Retry
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
