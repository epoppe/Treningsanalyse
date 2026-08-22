/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',
  compiler: {
    styledComponents: true,
  },
  async rewrites() {
    const api = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
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
