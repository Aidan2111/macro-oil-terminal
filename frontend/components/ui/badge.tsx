import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-pill border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-primary text-navy-950 hover:bg-primary/90",
        secondary:
          "border-transparent bg-bg-3 text-text-primary hover:bg-bg-3/80",
        destructive:
          "border-transparent bg-destructive text-destructive-foreground hover:bg-destructive/90",
        outline: "border-border text-text-primary",
        positive:
          "border-transparent bg-emerald-500/15 text-emerald-500",
        warn: "border-transparent bg-amber-400/15 text-amber-400",
        alert: "border-transparent bg-rose-500/15 text-rose-500",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
