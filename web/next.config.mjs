/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static export: `next build` emits a folder of static assets (web/out) that
  // FastAPI serves directly. No Node process at runtime.
  output: "export",
  images: { unoptimized: true },
  trailingSlash: true,
};

export default nextConfig;
