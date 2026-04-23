/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  experimental: {
    // Next.js 15 ships these out of experimental, kept here as a
    // parking lot for future tweaks (optimizePackageImports etc).
  },
  // The SWA config rewrites /api/* to the backend; `rewrites` here is
  // a belt-and-braces for local dev with `next dev` + a side-car
  // `uvicorn backend.main:app`.
  async rewrites() {
    if (process.env.NODE_ENV !== "development") return [];
    return [
      {
        source: "/api/:path*",
        destination: "http://127.0.0.1:8000/api/:path*",
      },
    ];
  },
};

export default nextConfig;
