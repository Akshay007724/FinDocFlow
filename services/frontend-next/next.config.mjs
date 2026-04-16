/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
  experimental: {
    typedRoutes: false,
  },
  async rewrites() {
    const ingestion = process.env.NEXT_PUBLIC_INGESTION_URL ?? "http://localhost:8001";
    const extraction = process.env.NEXT_PUBLIC_EXTRACTION_URL ?? "http://localhost:8002";
    const entity = process.env.NEXT_PUBLIC_ENTITY_LINKING_URL ?? "http://localhost:8003";
    const reasoning = process.env.NEXT_PUBLIC_REASONING_URL ?? "http://localhost:8004";
    return [
      { source: "/api/ingestion/:path*", destination: `${ingestion}/:path*` },
      { source: "/api/extraction/:path*", destination: `${extraction}/:path*` },
      { source: "/api/entity-linking/:path*", destination: `${entity}/:path*` },
      { source: "/api/reasoning/:path*", destination: `${reasoning}/:path*` },
    ];
  },
};
export default nextConfig;
