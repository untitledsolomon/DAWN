/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // vega-embed is loaded dynamically at runtime via ChartRenderer.
  // Exclude it from webpack bundling to prevent build-time resolution errors.
  serverExternalPackages: ["vega-embed", "vega", "vega-lite"],
  webpack: (config, { isServer }) => {
    // Prevent webpack from trying to resolve vega-embed at build time
    config.externals = config.externals || [];
    if (isServer) {
      config.externals.push("vega-embed", "vega", "vega-lite");
    }
    return config;
  },
};

export default nextConfig;
