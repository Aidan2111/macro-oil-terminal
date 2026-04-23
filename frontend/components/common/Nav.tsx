"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LineChart,
  Briefcase,
  Globe2,
  Home as HomeIcon,
} from "lucide-react";

type NavItem = {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
};

const ITEMS: NavItem[] = [
  { href: "/", label: "Home", icon: HomeIcon },
  { href: "/positions", label: "Positions", icon: Briefcase },
  { href: "/macro", label: "Macro", icon: LineChart },
  { href: "/fleet", label: "Fleet", icon: Globe2 },
];

/**
 * Sticky left rail on lg:+ viewports, bottom-tab bar below. Active
 * state highlights the current route. Safe-area padding on mobile so
 * the iOS home indicator doesn't overlap the icons.
 */
export function Nav() {
  const pathname = usePathname();

  return (
    <>
      {/* Desktop rail */}
      <aside
        aria-label="Primary navigation"
        className="hidden lg:flex fixed top-0 left-0 bottom-0 w-56 flex-col border-r border-border bg-bg-2 px-3 py-6 gap-1 z-20"
      >
        <div className="px-3 pb-6 text-sm font-semibold tracking-wide text-text-primary">
          Macro Oil Terminal
        </div>
        {ITEMS.map((item) => {
          const active =
            pathname === item.href ||
            (item.href !== "/" && pathname?.startsWith(item.href));
          return (
            <Link
              key={item.href}
              href={item.href}
              className={[
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm",
                active
                  ? "bg-bg-3 text-primary"
                  : "text-text-secondary hover:bg-bg-3 hover:text-text-primary",
              ].join(" ")}
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </aside>

      {/* Mobile bottom bar */}
      <nav
        aria-label="Primary navigation"
        className="lg:hidden fixed bottom-0 inset-x-0 z-20 flex justify-around border-t border-border bg-bg-2 pb-[env(safe-area-inset-bottom)]"
      >
        {ITEMS.map((item) => {
          const active =
            pathname === item.href ||
            (item.href !== "/" && pathname?.startsWith(item.href));
          return (
            <Link
              key={item.href}
              href={item.href}
              className={[
                "flex flex-col items-center justify-center gap-0.5 py-2 text-[11px]",
                active ? "text-primary" : "text-text-secondary",
              ].join(" ")}
            >
              <item.icon className="h-5 w-5" />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </>
  );
}
