/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Build a self-contained server bundle so the Docker runtime stage stays small.
  output: "standalone",
  // Keep the dev-mode overlay badge out of captured evidence screenshots (dev-only).
  devIndicators: false,
};

module.exports = nextConfig;
