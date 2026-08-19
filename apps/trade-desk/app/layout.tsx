import type { Metadata, Viewport } from "next";
import { Noto_Sans_JP } from "next/font/google";
import "./globals.css";

/** メイリオ系の見え方に近い、プレゼンでも見栄えするゴシック */
const sans = Noto_Sans_JP({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-sans-next",
  display: "swap",
});

export const metadata: Metadata = {
  title: "KURASHIFT｜クラシフト",
  description: "暮らしを整え、資産を動かす — ライフプラン軌道の資産運用HQ",
  applicationName: "KURASHIFT",
};

export const viewport: Viewport = {
  themeColor: "#1f4e79",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ja" className={sans.variable}>
      <body>{children}</body>
    </html>
  );
}
