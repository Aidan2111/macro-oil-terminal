/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  experimental: {
    // Next.js 15 ships these out of experimental, kept here as a
    // parking lot for future tweaks (optimizePackageImports etc).
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
