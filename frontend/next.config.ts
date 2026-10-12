import type { NextConfig } from "next";

const backendUrl = process.env.BACKEND_URL;

if (!backendUrl) {
  throw new Error(
    "BACKEND_URL is required. Copy frontend/.env.example to frontend/.env.local.",
  );
}

let normalizedBackendUrl: string;
try {
  const parsed = new URL(backendUrl);
  if (!['http:', 'https:'].includes(parsed.protocol)) {
    throw new Error("protocol must be http or https");
  }
  normalizedBackendUrl = parsed.toString().replace(/\/$/, "");
} catch (error) {
  throw new Error(`BACKEND_URL must be a valid HTTP(S) URL: ${String(error)}`);
}

const nextConfig: NextConfig = {
  agentRules: false,
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${normalizedBackendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;

