import { Timer } from "lucide-react";
import { cn } from "@/lib/utils";

type Props = {
  hoursToEia: number | null;
  className?: string;
};

function formatHours(hours: number): string {
  if (hours < 1) return "<1h";
  if (hours < 24) return `${Math.floor(hours)}h`;
  const days = Math.floor(hours / 24);
  // Truncate (not round) the leftover so 62.5h renders "2d 14h" rather
  // than "2d 15h" — matches the Streamlit countdown copy.
  const leftover = Math.floor(hours - days * 24);
  return `${days}d ${leftover}h`;
}

/**
 * Tiny meta-line under the hero card: either an EIA-release countdown
 * or the "no scheduled catalyst" fallback. Styled per the hero brief
 * (primary tint when there is a catalyst, secondary when not).
 */
export function CatalystCountdown({ hoursToEia, className }: Props) {
  const hasCatalyst = hoursToEia !== null && hoursToEia >= 0;
  return (
    <div
      data-testid="catalyst-countdown"
      className={cn(
        "inline-flex items-center gap-1.5 text-xs",
        hasCatalyst ? "text-primary" : "text-text-secondary",
        className,
      )}
    >
      <Timer className="h-3.5 w-3.5" aria-hidden />
      {hasCatalyst ? (
        <span>EIA release in {formatHours(hoursToEia as number)}</span>
      ) : (
        <span>No scheduled catalyst</span>
      )}
    </div>
  );
}
