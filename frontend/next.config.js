/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',
  compiler: {
    styledComponents: true,
  },
  // API proxy is handled at runtime by src/middleware.ts (desktop-friendly ports).
  // Keep rewrites as a fallback for older Next behavior / tooling that expects them.
  async rewrites() {
    if (process.env.DESKTOP_RUNTIME_PROXY === '1') {
      return [];
    }
    const api = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
    return [
      {
        source: '/api/:path*',
        destination: `${api}/api/:path*`,
      },
      {
        source: '/health',
        destination: `${api}/health`,
      },
      {
        source: '/health/:path*',
        destination: `${api}/health/:path*`,
      },
    ];
  },
  experimental: {
    optimizePackageImports: ['@tremor/react', 'recharts'],
  },
  webpack: (config) => {
    config.resolve.fallback = {
      ...config.resolve.fallback,
      fs: false,
    };
    return config;
  },
};

module.exports = nextConfig;
