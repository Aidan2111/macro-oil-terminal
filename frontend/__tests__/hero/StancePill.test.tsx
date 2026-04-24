import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { StancePill } from "@/components/hero/StancePill";

afterEach(() => cleanup());

describe("StancePill", () => {
  it.each([
    ["LONG_SPREAD", "Lean long"],
    ["SHORT_SPREAD", "Lean short"],
    ["FLAT", "Stand aside"],
    ["STAND_ASIDE", "Stand aside"],
  ] as const)("renders %s as '%s' with correct data-stance", (stance, copy) => {
    render(<StancePill stance={stance} />);
    const pill = screen.getByTestId("stance-pill");
    expect(pill).toHaveAttribute("data-stance", stance);
    // Copy is UPPER-cased via CSS but the text content is the plain phrase.
    expect(pill.textContent?.toLowerCase()).toContain(copy.toLowerCase());
  });
});
