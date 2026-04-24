import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { ConfidenceBar } from "@/components/hero/ConfidenceBar";

afterEach(() => cleanup());

describe("ConfidenceBar", () => {
  it.each([
    [1, "Low"],
    [3, "Low"],
    [4, "Medium"],
    [5, "Medium"],
    [6, "Medium"],
    [7, "High"],
    [8, "High"],
    [9, "Very High"],
    [10, "Very High"],
  ])("value %i renders band %s", (value, band) => {
    render(<ConfidenceBar value={value} stance="LONG_SPREAD" />);
    expect(
      screen.getByText(new RegExp(`${band}\\s*\\(${value}/10\\)`)),
    ).toBeInTheDocument();
  });

  it("sets aria attributes correctly", () => {
    render(<ConfidenceBar value={7} stance="LONG_SPREAD" />);
    const bar = screen.getByTestId("confidence-bar");
    expect(bar).toHaveAttribute("role", "progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "7");
    expect(bar).toHaveAttribute("aria-valuemin", "0");
    expect(bar).toHaveAttribute("aria-valuemax", "10");
    expect(bar).toHaveAttribute("data-confidence", "7");
  });

  it("fill width tracks value*10 percent", () => {
    render(<ConfidenceBar value={4} stance="LONG_SPREAD" />);
    const fill = screen.getByTestId("confidence-bar-fill");
    // Framer-motion `animate` drops the target width onto inline style
    // synchronously on mount in jsdom (no real RAF tick).
    expect(fill.getAttribute("style") ?? "").toMatch(/width:\s*40%/);
  });

  it("clamps extreme values to the [0,10] range", () => {
    render(<ConfidenceBar value={15} stance="LONG_SPREAD" />);
    const bar = screen.getByTestId("confidence-bar");
    expect(bar).toHaveAttribute("aria-valuenow", "10");
  });
});
