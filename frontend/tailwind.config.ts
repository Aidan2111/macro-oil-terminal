import type { Config } from "tailwindcss";

// Palette tokens wired via CSS custom properties in styles/tokens.css.
// Keep this file lean — tokens are the source of truth.
const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        "bg-1": "var(--bg-1)",
        "bg-2": "var(--bg-2)",
        "bg-3": "var(--bg-3)",
        border: "var(--border)",
        "text-primary": "var(--text-primary)",
        "text-secondary": "var(--text-secondary)",
        "text-muted": "var(--text-muted)",
        primary: "var(--primary)",
        "primary-glow": "var(--primary-glow)",
        warn: "var(--warn)",
        alert: "var(--alert)",
        positive: "var(--positive)",
        negative: "var(--negative)",
        gridline: "var(--gridline)",
      },
      fontFamily: {
        sans: [
          "Inter",
          "'Source Sans Pro'",
          "-apple-system",
          "'Segoe UI'",
          "sans-serif",
        ],
        mono: [
          "'JetBrains Mono'",
          "ui-monospace",
          "SFMono-Regular",
          "monospace",
        ],
      },
    },
  },
  plugins: [],
};

export default config;
