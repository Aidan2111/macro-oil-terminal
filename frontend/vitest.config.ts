import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

/**
 * Vitest config for the Next.js frontend. jsdom environment so we can
 * mount React components and test DOM-level behaviour without a real
 * browser (and, crucially, without WebGPU — components must degrade
 * gracefully there). `@vitejs/plugin-react` compiles TSX; `esbuild.jsx:
 * automatic` kept as a belt-and-braces so pre-plugin imports transform
 * cleanly.
 */
export default defineConfig({
  plugins: [react()],
  esbuild: {
    jsx: "automatic",
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    // Both setup files participate: Sub-D's ./__tests__/setup.ts handles
    // @testing-library/jest-dom; Sub-E's ./vitest.setup.ts adds the
    // WebGPU/navigator.gpu shim for the globe component.
    setupFiles: ["./__tests__/setup.ts", "./vitest.setup.ts"],
    include: ["__tests__/**/*.{test,spec}.{ts,tsx}"],
    css: false,
  },
});
