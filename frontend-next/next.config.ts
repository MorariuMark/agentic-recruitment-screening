import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  allowedDevOrigins: [
    "127.0.0.1",
    "127.0.0.1:3000",
    "localhost",
    "localhost:3000",
  ],
  devIndicators: {
    position: "bottom-right",
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://127.0.0.1:8000/api/:path*",
      },
      {
        source: "/health",
        destination: "http://127.0.0.1:8000/health",
      },
    ];
  },
};

export default nextConfig;

