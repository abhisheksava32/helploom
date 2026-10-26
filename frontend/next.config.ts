import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV !== "production";
const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const wsUrl = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";

function origin(url: string): string {
  try {
    return new URL(url).origin;
  } catch {
    return url;
  }
}

// Next.js streams its payload in inline scripts, and nonces would force every page
// to render per request, so scripts allow 'unsafe-inline' but no other origins.
// connect-src is the part that matters most: the dashboard may only talk to the API.
const contentSecurityPolicy = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self'",
  `connect-src 'self' ${origin(apiUrl)} ${origin(wsUrl)}${isDev ? " ws://localhost:* ws://127.0.0.1:*" : ""}`,
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: contentSecurityPolicy },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
];

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
  async headers() {
    return [
      { source: "/:path*", headers: securityHeaders },
      {
        // The widget is loaded by customer sites: cache it briefly so a release
        // reaches every site within minutes, and allow cross origin embedding.
        source: "/widget.js",
        headers: [
          { key: "Cache-Control", value: "public, max-age=300, stale-while-revalidate=86400" },
          { key: "Cross-Origin-Resource-Policy", value: "cross-origin" },
          { key: "Access-Control-Allow-Origin", value: "*" },
        ],
      },
    ];
  },
};

export default nextConfig;
