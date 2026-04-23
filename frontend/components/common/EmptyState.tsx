import { Info } from "lucide-react";

type Props = {
  title: string;
  message?: string;
  cta?: { label: string; onClick: () => void };
};

/**
 * Centred, quiet "nothing here yet" slot. One line of copy, optional
 * CTA. Icon is Lucide's Info — keeps iconography to a single family.
 */
export function EmptyState({ title, message, cta }: Props) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-10 text-center">
      <Info className="h-8 w-8 text-text-muted" aria-hidden />
      <div className="text-sm font-medium text-text-primary">{title}</div>
      {message ? (
        <div className="text-xs text-text-secondary max-w-md">{message}</div>
      ) : null}
      {cta ? (
        <button
          type="button"
          onClick={cta.onClick}
          className="mt-2 rounded-md border border-border bg-bg-3 px-3 py-1.5 text-xs text-text-primary hover:border-primary"
        >
          {cta.label}
        </button>
      ) : null}
    </div>
  );
}
