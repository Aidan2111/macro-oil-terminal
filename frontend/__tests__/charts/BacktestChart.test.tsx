import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { BacktestChart } from "@/components/charts/BacktestChart";
import { makeBacktestFixture } from "../fixtures/backtest";

describe("BacktestChart", () => {
  it("renders the equity-curve chart and summary stats", () => {
    const data = makeBacktestFixture();
    const { container } = render(<BacktestChart data={data} />);
    expect(screen.getByTestId("backtest-chart")).toBeInTheDocument();
    expect(container.querySelector("svg")).not.toBeNull();
    // Summary row surfaces Sharpe / Sortino / Calmar / Hit / Max DD.
    const root = screen.getByTestId("backtest-chart");
    expect(root.textContent ?? "").toMatch(/Sharpe/i);
    expect(root.textContent ?? "").toMatch(/Sortino/i);
    expect(root.textContent ?? "").toMatch(/Calmar/i);
    expect(root.textContent ?? "").toMatch(/Hit/i);
    expect(root.textContent ?? "").toMatch(/Max DD/i);
  });

  it("renders an EmptyState when the curve is empty", () => {
    const data = makeBacktestFixture(0);
    render(<BacktestChart data={{ ...data, equity_curve: [] }} />);
    expect(screen.getByText(/no backtest/i)).toBeInTheDocument();
  });

  it("renders an ErrorState when error prop is set", () => {
    render(<BacktestChart data={null} error="backtest failed" />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});
