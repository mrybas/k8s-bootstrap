/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000';
    return [
      // API endpoints
      {
        source: '/api/:path*',
        destination: `${backendUrl}/api/:path*`,
      },
      // Bootstrap script endpoint (one-time download)
      {
        source: '/bootstrap/:token',
        destination: `${backendUrl}/bootstrap/:token`,
      },
      // Update script endpoint (one-time download)
      {
        source: '/update/:token',
        destination: `${backendUrl}/update/:token`,
      },
    ];
  },
};

module.exports = nextConfig;
