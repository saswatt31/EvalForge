import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: process.env.NEXT_OUTPUT_STANDALONE === "true" ? "standalone" : undefined,
  outputFileTracingRoot: path.resolve("."),
  reactStrictMode: true,
  eslint: {
    // Lint is a separate CI step; avoid running it twice during production builds.
    ignoreDuringBuilds: true,
  },
};

export default nextConfig;
