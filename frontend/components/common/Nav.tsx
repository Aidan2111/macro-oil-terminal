"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LineChart,
  Briefcase,
  Globe2,
  Home as HomeIcon,
  History,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
};

const ITEMS: NavItem[] = [
  { href: "/", label: "Home", icon: HomeIcon },
  { href: "/macro", label: "Macro", icon: LineChart },
  { href: "/fleet", label: "Fleet", icon: Globe2 },
  { href: "/positions", label: "Positions", icon: Briefcase },
  { href: "/track-record", label: "Track Record", icon: History },
];

function isActive(pathname: string | null, href: string): boolean {
  if (!pathname) return false;
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

/**
 * Primary navigation. On `md:+` viewports (>=768px) renders a sticky
 * left rail (w-60 fixed). Below that, renders a bottom tab bar
 * (h-16 fixed). Active route is highlighted in cyan.
 */
export function Nav() {
  const pathname = usePathname();

  return (
    <>
      {/* Desktop rail */}
      <aside
        aria-label="Primary navigation"
        data-testid="nav-desktop"
        className="hidden md:flex fixed top-0 left-0 bottom-0 w-60 flex-col border-r border-border bg-bg-2 px-3 py-6 gap-1 z-20"
      >
        <div className="px-3 pb-6 text-sm font-semibold tracking-wide text-text-primary">
          Macro Oil Terminal
        </div>
        {ITEMS.map((item) => {
          const active = isActive(pathname, item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                // min-h-[44px] hits the WCAG AA / Apple HIG touch-target
                // floor; previously the rail link rendered at 36px tall.
                "flex items-center gap-3 rounded-btn px-3 py-2 text-sm min-h-[44px]",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-bg-1",
                active
                  ? "bg-bg-3 text-primary"
                  : "text-text-secondary hover:bg-bg-3 hover:text-text-primary",
              )}
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
        data-testid="nav-mobile"
        className="md:hidden fixed bottom-0 inset-x-0 z-20 flex h-16 justify-around border-t border-border bg-bg-2 pb-[env(safe-area-inset-bottom)]"
      >
        {ITEMS.map((item) => {
          const active = isActive(pathname, item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex flex-col items-center justify-center gap-0.5 py-2 text-[11px] flex-1",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-inset",
                active ? "text-primary" : "text-text-secondary",
              )}
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
