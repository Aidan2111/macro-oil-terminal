import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type Props = {
  lines?: number;
  height?: string;
  className?: string;
};

/**
 * Stack of shimmering Skeleton bars. Wraps the shadcn primitive so
 * call-sites stay terse.
 */
export function LoadingSkeleton({
  lines = 3,
  height = "h-4",
  className,
}: Props) {
  return (
    <div className={cn("space-y-2", className)} aria-hidden>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          className={height}
          style={{ width: `${80 + ((i * 13) % 20)}%` }}
        />
      ))}
    </div>
  );
}
