import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { CatalystCountdown } from "@/components/hero/CatalystCountdown";

afterEach(() => cleanup());

describe("CatalystCountdown", () => {
  it("formats 62.5 hours as '2d 14h'", () => {
    render(<CatalystCountdown hoursToEia={62.5} />);
    expect(screen.getByTestId("catalyst-countdown")).toHaveTextContent(
      /EIA release in 2d 14h/i,
    );
  });

  it("renders the no-catalyst copy when null", () => {
    render(<CatalystCountdown hoursToEia={null} />);
    expect(screen.getByTestId("catalyst-countdown")).toHaveTextContent(
      /No scheduled catalyst/i,
    );
  });

  it("renders < 24h with just hours", () => {
    render(<CatalystCountdown hoursToEia={5.25} />);
    expect(screen.getByTestId("catalyst-countdown")).toHaveTextContent(
      /EIA release in 5h/i,
    );
  });
});
