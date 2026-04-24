import { defineConfig } from "vitest/config";
import path from "node:path";

/**
 * Vitest config for the Next.js frontend. jsdom environment so we can
 * mount React components and test DOM-level behaviour without a real
 * browser (and, crucially, without WebGPU — components must degrade
 * gracefully there).
 */
export default defineConfig({
  esbuild: {
    jsx: "automatic",
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["__tests__/**/*.test.{ts,tsx}"],
    css: false,
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./"),
    },
  },
});
