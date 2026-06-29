/** @type {import('next').NextConfig} */
const nextConfig = {
  transpilePackages: ["@rag-console/ui", "@rag-console/shared-types"],
  output: "standalone",
};

export default nextConfig;
