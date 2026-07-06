/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Don't bundle vega packages on the server — they're only used client-side via dynamic import
  serverExternalPackages: ["vega-embed", "vega", "vega-lite"],
  webpack: (config, { isServer }) => {
    if (isServer) {
      // Prevent webpack from trying to resolve vega packages during server build
      config.externals = [...(config.externals || []), "vega-embed", "vega", "vega-lite"];
    }
    return config;
  },
};

export default nextConfig;
