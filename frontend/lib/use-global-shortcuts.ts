"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export type ShortcutHandler = () => void;

export type ShortcutMap = Record<string, ShortcutHandler>;

/**
 * Returns true if the event target is an editable surface — input,
 * textarea, contenteditable. Single-letter shortcuts must skip these
 * so the user can type into forms without triggering navigation.
 */
function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  if (target.isContentEditable) return true;
  return false;
}

/**
 * Bind a top-level keymap. Letters route to pages; the special
 * `?` key (Shift+/) opens the shortcut sheet via the `onHelp`
 * callback passed by the host. The hook is no-op on the server.
 */
export function useGlobalShortcuts({
  onHelp,
}: {
  onHelp: () => void;
}): void {
  const router = useRouter();

  useEffect(() => {
    if (typeof window === "undefined") return;
    const handler = (e: KeyboardEvent) => {
      // Modifiers (Cmd / Ctrl / Alt / Meta) → never own a shortcut.
      // We want g/m/f/p/t and ? to work, never collide with browser
      // chrome or shadow inputs.
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (isEditableTarget(e.target)) return;
      const key = e.key;

      // ?, Shift+/  → open help sheet
      if (key === "?" || (e.shiftKey && key === "/")) {
        e.preventDefault();
        onHelp();
        return;
      }

      // Single-letter route shortcuts.
      switch (key) {
        case "g":
          e.preventDefault();
          router.push("/");
          return;
        case "m":
          e.preventDefault();
          router.push("/macro");
          return;
        case "f":
          e.preventDefault();
          router.push("/fleet");
          return;
        case "p":
          e.preventDefault();
          router.push("/positions");
          return;
        case "t":
          e.preventDefault();
          router.push("/track-record");
          return;
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [router, onHelp]);
}
