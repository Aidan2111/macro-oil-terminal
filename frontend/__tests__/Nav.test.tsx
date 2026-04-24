import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { Nav } from "@/components/common/Nav";

// next/navigation's usePathname is a server/client hook — stub it.
vi.mock("next/navigation", () => ({
  usePathname: () => "/macro",
}));

// next/link in an isolated jsdom test just renders an anchor.
vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...rest
  }: React.PropsWithChildren<{ href: string } & Record<string, unknown>>) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

describe("Nav", () => {
  it("renders all five primary links", () => {
    render(<Nav />);
    // Each link appears in both the desktop rail and mobile tab bar.
    expect(screen.getAllByRole("link", { name: /home/i })).toHaveLength(2);
    expect(screen.getAllByRole("link", { name: /macro/i })).toHaveLength(2);
    expect(screen.getAllByRole("link", { name: /fleet/i })).toHaveLength(2);
    expect(screen.getAllByRole("link", { name: /positions/i })).toHaveLength(
      2,
    );
    expect(
      screen.getAllByRole("link", { name: /track record/i }),
    ).toHaveLength(2);
  });

  it("highlights the active route via aria-current", () => {
    render(<Nav />);
    const actives = screen.getAllByRole("link", { name: /macro/i });
    actives.forEach((el) => {
      expect(el).toHaveAttribute("aria-current", "page");
    });

    const inactive = screen.getAllByRole("link", { name: /home/i })[0];
    expect(inactive).not.toHaveAttribute("aria-current");
  });

  it("exposes desktop and mobile nav surfaces", () => {
    render(<Nav />);
    const desktop = screen.getByTestId("nav-desktop");
    const mobile = screen.getByTestId("nav-mobile");

    // Desktop is hidden below md:, mobile is hidden above md:.
    expect(desktop.className).toContain("hidden");
    expect(desktop.className).toContain("md:flex");
    expect(mobile.className).toContain("md:hidden");
    expect(mobile.className).toContain("h-16");
    expect(mobile.className).toContain("fixed");
  });
});
