import { AlertTriangle } from "lucide-react";

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
      className="rounded-md border border-alert/40 bg-alert/10 p-4 text-sm text-text-primary"
    >
      <div className="flex items-start gap-3">
        <AlertTriangle className="h-5 w-5 text-alert shrink-0" aria-hidden />
        <div className="flex-1 space-y-2">
          <div>{message}</div>
          {retry ? (
            <button
              type="button"
              onClick={retry}
              className="rounded-md border border-border bg-bg-3 px-3 py-1 text-xs text-text-primary hover:border-primary"
            >
              Retry
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
