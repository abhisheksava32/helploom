import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Pages render their static shell at build time and stream the rest.
  cacheComponents: true,
  partialPrefetching: true,
  // Stop `next dev` from writing instruction files into the repository.
  agentRules: false,
  poweredByHeader: false,
  // Self-contained server bundle for the production image (frontend/Dockerfile).
  output: "standalone",
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
