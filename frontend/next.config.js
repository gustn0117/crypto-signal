/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  env: {
    NEXT_PUBLIC_BUILD_TIME: new Date().toISOString(),
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:8000/api/:path*",
      },
    ];
  },
};

module.exports = nextConfig;
