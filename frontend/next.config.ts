import type { NextConfig } from "next";
const config: NextConfig = {
  devIndicators: false,
  async rewrites() {
    const backend = process.env.BACKEND_URL || "http://127.0.0.1:8000";
    return [
      { source: "/api/:path*", destination: `${backend}/api/:path*` },
      ...["login", "signup", "logout", "profile", "resend-confirmation"].map((path) => ({
        source: `/${path}`,
        destination: `${backend}/${path}`,
      })),
    ];
  },
};
export default config;
