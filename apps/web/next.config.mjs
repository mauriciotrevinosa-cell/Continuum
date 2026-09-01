/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // CONTINUUM_API_BASE is deliberately NOT declared here. next.config `env`
  // inlines values at BUILD time; every page that talks to the API is a
  // server component marked `force-dynamic`, so reading process.env at
  // request time means the API address can change without a rebuild.
};

export default nextConfig;
