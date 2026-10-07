/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  allowedDevOrigins: ["127.0.0.1"],
  devIndicators: false,
  outputFileTracingRoot: __dirname,
  turbopack: { root: __dirname },
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

module.exports = nextConfig;
