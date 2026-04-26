import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Static export so every route lands as its own HTML file. SWA hosts
  // out/ as plain static; client-side fetch hits the FastAPI backend
  // cross-origin via NEXT_PUBLIC_API_URL.
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  experimental: {
    // Tree-shake recharts (notorious D3 chain), lucide icon set, and
    // framer-motion's nested module surface — review #13 axis 5.
    optimizePackageImports: ["recharts", "lucide-react", "framer-motion"],
  },
  // three.js r169: `three`, `three/webgpu`, and `three/tsl` are three different
  // subpath imports. Per node_modules/three/package.json `exports`, both
  // `three/webgpu` and `three/tsl` resolve to the SAME file
  // (`build/three.webgpu.js`), and that file re-exports the core from
  // `three.module.js`. Without bundler intervention webpack creates separate
  // module records for each entry point in different chunks, causing three's
  // own runtime guard `if (globalThis.__THREE__) console.warn("Multiple
  // instances of Three.js being imported.")` to fire on hydration.
  //
  // Two-pronged fix:
  //
  // 1. Pin every subpath to a single canonical file via an explicit alias,
  //    so the bundler skips its `exports` resolver and dedupes by absolute
  //    path. Both `three/webgpu` and `three/tsl` map to the same JS file —
  //    matching what package.json exports already says, just enforced.
  //
  // 2. Force three into a shared async chunk via `splitChunks.cacheGroups`
  //    so dynamic-imported modules from FleetGlobe + HeroShaderBackground
  //    end up in ONE chunk instead of duplicating three across both.
  webpack: (config) => {
    const threeRoot = path.resolve(__dirname, "node_modules/three");
    const threeModule = path.join(threeRoot, "build/three.module.js");
    const threeWebgpu = path.join(threeRoot, "build/three.webgpu.js");
    config.resolve = config.resolve || {};
    config.resolve.alias = {
      ...(config.resolve.alias || {}),
      // Exact match (`$` suffix in webpack alias semantics) so subpaths
      // like `three/webgpu` keep going through their own resolver entry.
      three$: threeModule,
      "three/webgpu$": threeWebgpu,
      "three/tsl$": threeWebgpu,
    };
    config.optimization = config.optimization || {};
    config.optimization.splitChunks = config.optimization.splitChunks || {};
    config.optimization.splitChunks.cacheGroups = {
      ...(config.optimization.splitChunks.cacheGroups || {}),
      three: {
        name: "three",
        test: /[\\/]node_modules[\\/]three[\\/]/,
        chunks: "all",
        priority: 30,
        reuseExistingChunk: true,
      },
    };
    return config;
  },
  // /api/* is proxied at the Next.js layer (works on Static Web Apps
  // hybrid mode where staticwebapp.config.json routes lose to Next.js
  // routing). Local dev hits the side-car uvicorn; production hits the
  // canadaeast App Service.
  async rewrites() {
    const apiBase =
      process.env.NEXT_PUBLIC_API_URL ||
      (process.env.NODE_ENV === "development"
        ? "http://127.0.0.1:8000"
        : "https://oil-tracker-api-canadaeast-0f18.azurewebsites.net");
    return [
      {
        source: "/api/:path*",
        destination: `${apiBase}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
