/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  experimental: {
    // AutoSnore スクショ2枚（元画像が大きい）を Server Action で受け取る
    serverActions: {
      bodySizeLimit: "8mb",
    },
  },
  // グルコン成果報告の配点 CSV（fs 読込）をサーバレスに同梱
  outputFileTracingIncludes: {
    "/glucon": ["./lib/glucon/scoring_seed.csv"],
    "/*": ["./lib/glucon/scoring_seed.csv"],
  },
};

module.exports = nextConfig;
