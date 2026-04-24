import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { SpreadChart } from "@/components/charts/SpreadChart";
import { makeSpreadFixture } from "../fixtures/spread";

describe("SpreadChart", () => {
  it("renders a chart container when data is present", () => {
    const data = makeSpreadFixture().history;
    const { container } = render(<SpreadChart data={data} />);
    expect(screen.getByTestId("spread-chart")).toBeInTheDocument();
    // Recharts creates an <svg> inside the container.
    expect(container.querySelector("svg")).not.toBeNull();
  });

  it("exposes an aria-label describing the chart", () => {
    const data = makeSpreadFixture().history;
    render(<SpreadChart data={data} />);
    const root = screen.getByTestId("spread-chart");
    expect(root.getAttribute("aria-label")).toMatch(/spread/i);
  });

  it("renders an EmptyState on empty series", () => {
    render(<SpreadChart data={[]} />);
    expect(screen.getByTestId("spread-chart")).toBeInTheDocument();
    expect(screen.getByText(/no spread data/i)).toBeInTheDocument();
  });

  it("renders an ErrorState when error prop is set", () => {
    render(<SpreadChart data={[]} error="upstream down" />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});
