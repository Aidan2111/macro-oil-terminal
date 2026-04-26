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
