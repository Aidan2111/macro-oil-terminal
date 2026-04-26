"use client";

import * as React from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useGlobalShortcuts } from "@/lib/use-global-shortcuts";

const ROWS: Array<{ keys: string; label: string }> = [
  { keys: "g", label: "Go to Home" },
  { keys: "m", label: "Go to Macro" },
  { keys: "f", label: "Go to Fleet" },
  { keys: "p", label: "Go to Positions" },
  { keys: "t", label: "Go to Track Record" },
  { keys: "?", label: "Open this shortcut sheet" },
  { keys: "Esc", label: "Close any open dialog" },
];

/**
 * Global keyboard shortcut sheet. The hook installs a single keydown
 * listener on `window`; when the user presses `?` (Shift+/) outside an
 * input we open the modal. Letter shortcuts route via Next.js's
 * client router. Mounted once in `app/layout.tsx`.
 */
export function ShortcutSheet() {
  const [open, setOpen] = React.useState(false);
  useGlobalShortcuts({ onHelp: () => setOpen(true) });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent
        data-testid="shortcut-sheet"
        className="max-w-md"
        aria-label="Keyboard shortcuts"
      >
        <DialogHeader>
          <DialogTitle>Keyboard shortcuts</DialogTitle>
          <DialogDescription>
            Press a single letter from any page (outside an input).
          </DialogDescription>
        </DialogHeader>
        <ul className="divide-y divide-border text-sm">
          {ROWS.map((r) => (
            <li
              key={r.keys}
              className="flex items-center justify-between py-2"
            >
              <span className="text-text-secondary">{r.label}</span>
              <kbd className="rounded-btn border border-border bg-bg-3 px-2 py-0.5 font-mono text-xs text-text-primary">
                {r.keys}
              </kbd>
            </li>
          ))}
        </ul>
      </DialogContent>
    </Dialog>
  );
}
