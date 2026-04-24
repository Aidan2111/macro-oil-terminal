import * as React from "react";
import { cn } from "@/lib/utils";

type SectionProps = {
  id?: string;
  title?: string;
  subtitle?: string;
  className?: string;
  children: React.ReactNode;
};

type SectionHeaderProps = {
  title: string;
  subtitle?: string;
  className?: string;
};

/**
 * Header block for a Section — keeps page copy consistent across
 * routes. Exported standalone so callers can compose their own
 * layouts when the default spacing doesn't fit.
 */
export function SectionHeader({
  title,
  subtitle,
  className,
}: SectionHeaderProps) {
  return (
    <header className={cn("space-y-1", className)}>
      <h2 className="text-xl font-semibold text-text-primary">{title}</h2>
      {subtitle ? (
        <p className="text-sm text-text-secondary">{subtitle}</p>
      ) : null}
    </header>
  );
}

/**
 * Vertical page section with optional header + consistent spacing.
 * All route pages should wrap their main content in one or more
 * <Section>s so padding stays uniform.
 */
export function Section({
  id,
  title,
  subtitle,
  className,
  children,
}: SectionProps) {
  return (
    <section id={id} className={cn("space-y-4 py-6", className)}>
      {title ? <SectionHeader title={title} subtitle={subtitle} /> : null}
      {children}
    </section>
  );
}
