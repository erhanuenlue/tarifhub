/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Build a self-contained server bundle so the Docker runtime stage stays small.
  output: "standalone",
  // Pin the file-tracing root to this app directory. The repo has sibling lockfiles
  // (apps/kassenflow, apps/meldepilot) and parent-directory lockfiles, any of which Next
  // could otherwise infer as the workspace root, emitting a warning and tracing files
  // outside the app into the standalone bundle. __dirname keeps tracing scoped here.
  outputFileTracingRoot: __dirname,
  // Keep the dev-mode overlay badge out of captured evidence screenshots (dev-only).
  devIndicators: false,
};

module.exports = nextConfig;
