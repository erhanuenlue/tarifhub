/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Build a self-contained server bundle so the Docker runtime stage stays small.
  output: "standalone",
};

module.exports = nextConfig;
