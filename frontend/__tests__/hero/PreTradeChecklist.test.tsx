import { describe, it, expect, afterEach, beforeEach } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { PreTradeChecklist } from "@/components/hero/PreTradeChecklist";
import type { ChecklistItem } from "@/types/api";

afterEach(() => cleanup());
beforeEach(() => {
  window.localStorage.clear();
});

const ITEMS: ChecklistItem[] = [
  { key: "stop_in_place", prompt: "I have a stop at ±2σ spread move from entry.", auto_check: null },
  { key: "vol_clamp_ok", prompt: "Spread realised vol is below the 1y 85th percentile.", auto_check: true },
  { key: "half_life_ack", prompt: "I understand the implied half-life is ~N days.", auto_check: null },
  { key: "catalyst_clear", prompt: "No EIA release within the next 24 hours.", auto_check: true },
  { key: "no_conflicting_recent_thesis", prompt: "No stance flip in the last 5 thesis entries.", auto_check: null },
];

describe("PreTradeChecklist", () => {
  it("renders all five items", () => {
    render(<PreTradeChecklist items={ITEMS} thesisId="t-1" />);
    ITEMS.forEach((item) => {
      expect(screen.getByText(item.prompt)).toBeInTheDocument();
    });
  });

  it("auto-checked items render checked regardless of localStorage", () => {
    // Seed localStorage with the auto-checked keys set to false — the
    // component must ignore this for auto-checked items.
    window.localStorage.setItem(
      "mot:preTradeChecklist:t-2",
      JSON.stringify({ vol_clamp_ok: false, catalyst_clear: false }),
    );
    render(<PreTradeChecklist items={ITEMS} thesisId="t-2" />);
    const volItem = screen.getByTestId("checklist-item-vol_clamp_ok");
    expect(volItem).toHaveAttribute("data-checked", "true");
    const catItem = screen.getByTestId("checklist-item-catalyst_clear");
    expect(catItem).toHaveAttribute("data-checked", "true");
  });

  it("user-toggleable items flip on click and persist to localStorage", () => {
    render(<PreTradeChecklist items={ITEMS} thesisId="t-3" />);
    const row = screen.getByTestId("checklist-item-stop_in_place");
    expect(row).toHaveAttribute("data-checked", "false");

    fireEvent.click(row);
    expect(row).toHaveAttribute("data-checked", "true");

    const raw = window.localStorage.getItem("mot:preTradeChecklist:t-3");
    expect(raw).not.toBeNull();
    const parsed = JSON.parse(raw!) as Record<string, boolean>;
    expect(parsed.stop_in_place).toBe(true);
  });

  it("hydrates user ticks from localStorage", () => {
    window.localStorage.setItem(
      "mot:preTradeChecklist:t-4",
      JSON.stringify({ half_life_ack: true }),
    );
    render(<PreTradeChecklist items={ITEMS} thesisId="t-4" />);
    expect(
      screen.getByTestId("checklist-item-half_life_ack"),
    ).toHaveAttribute("data-checked", "true");
  });

  it("tags the container with data-testid", () => {
    render(<PreTradeChecklist items={ITEMS} thesisId="t-5" />);
    expect(screen.getByTestId("pre-trade-checklist")).toBeInTheDocument();
  });
});
