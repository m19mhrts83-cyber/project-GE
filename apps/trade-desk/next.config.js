/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // クライアント/サーバ双方で unused export を削り、起動・遷移を軽くする
  experimental: {
    optimizePackageImports: ["@supabase/supabase-js", "@supabase/ssr"],
  },
};

module.exports = nextConfig;
