import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { InventoryChart } from "@/components/charts/InventoryChart";
import { makeInventoryFixture } from "../fixtures/inventory";

describe("InventoryChart", () => {
  it("renders a ComposedChart with the provided data", () => {
    const data = makeInventoryFixture();
    const { container } = render(
      <InventoryChart history={data.history} forecast={data.forecast} />,
    );
    expect(screen.getByTestId("inventory-chart")).toBeInTheDocument();
    expect(container.querySelector("svg")).not.toBeNull();
  });

  it("shows the projected floor breach date when present", () => {
    const data = makeInventoryFixture();
    render(
      <InventoryChart history={data.history} forecast={data.forecast} />,
    );
    const root = screen.getByTestId("inventory-chart");
    expect(root.textContent ?? "").toMatch(/2026-11-15|Forecast breach/i);
  });

  it("renders an EmptyState on empty history", () => {
    render(
      <InventoryChart
        history={[]}
        forecast={{
          daily_depletion_bbls: 0,
          weekly_depletion_bbls: 0,
          projected_floor_date: null,
          r_squared: 0,
          floor_bbls: 0,
        }}
      />,
    );
    expect(screen.getByText(/no inventory/i)).toBeInTheDocument();
  });

  it("renders an ErrorState when error prop is set", () => {
    render(
      <InventoryChart
        history={[]}
        forecast={null}
        error="EIA unreachable"
      />,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});
