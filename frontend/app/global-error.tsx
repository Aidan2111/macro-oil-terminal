"use client";

/**
 * Root error boundary. Next 15 requires this file to ship its own
 * <html> + <body> because RootLayout itself has crashed by the time we
 * get here. Keep it minimal — no Tailwind layout helpers, no providers —
 * just enough markup to tell the user what happened and offer a reload.
 */
import { useEffect } from "react";

type Props = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function GlobalError({ error, reset }: Props) {
  useEffect(() => {
    // eslint-disable-next-line no-console
    console.error("[global error]", error);
  }, [error]);

  return (
    <html lang="en">
      <body
        style={{
          background: "#0b1221",
          color: "#e2e8f0",
          fontFamily: "system-ui, -apple-system, Segoe UI, sans-serif",
          margin: 0,
          minHeight: "100vh",
          padding: "2rem",
        }}
      >
        <main
          role="alert"
          style={{
            maxWidth: 640,
            margin: "4rem auto",
            border: "1px solid rgba(244,63,94,0.4)",
            background: "rgba(244,63,94,0.1)",
            borderRadius: 12,
            padding: "1.5rem",
          }}
        >
          <h1 style={{ fontSize: "1.25rem", marginTop: 0 }}>
            Macro Oil Terminal hit an unrecoverable error
          </h1>
          <p style={{ fontSize: "0.875rem", lineHeight: 1.5 }}>
            {error.message || "The application crashed before it could render."}
          </p>
          <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem" }}>
            <button
              type="button"
              onClick={reset}
              style={btnStyle("solid")}
            >
              Try again
            </button>
            <button
              type="button"
              onClick={() => {
                if (typeof window !== "undefined") window.location.reload();
              }}
              style={btnStyle("outline")}
            >
              Reload page
            </button>
          </div>
        </main>
      </body>
    </html>
  );
}

function btnStyle(variant: "solid" | "outline"): React.CSSProperties {
  const base: React.CSSProperties = {
    fontSize: "0.875rem",
    padding: "0.5rem 0.875rem",
    borderRadius: 6,
    cursor: "pointer",
  };
  if (variant === "solid") {
    return { ...base, background: "#22d3ee", color: "#0b1221", border: "none" };
  }
  return {
    ...base,
    background: "transparent",
    color: "#e2e8f0",
    border: "1px solid rgba(226,232,240,0.4)",
  };
}
