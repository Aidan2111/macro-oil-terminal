import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { StretchChart } from "@/components/charts/StretchChart";
import { makeSpreadFixture } from "../fixtures/spread";

describe("StretchChart", () => {
  it("renders the chart container when data is present", () => {
    const data = makeSpreadFixture().history;
    const { container } = render(<StretchChart data={data} />);
    expect(screen.getByTestId("stretch-chart")).toBeInTheDocument();
    expect(container.querySelector("svg")).not.toBeNull();
  });

  it("labels the Calm and Very Stretched reference bands", () => {
    const data = makeSpreadFixture().history;
    render(<StretchChart data={data} />);
    const root = screen.getByTestId("stretch-chart");
    expect(root.textContent ?? "").toMatch(/Very Stretched/i);
    expect(root.textContent ?? "").toMatch(/Calm/i);
  });

  it("renders an EmptyState on empty series", () => {
    render(<StretchChart data={[]} />);
    expect(screen.getByText(/no stretch/i)).toBeInTheDocument();
  });

  it("renders an ErrorState when error prop is set", () => {
    render(<StretchChart data={[]} error="z-score unavailable" />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});
