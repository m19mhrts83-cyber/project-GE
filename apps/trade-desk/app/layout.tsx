import type { Metadata, Viewport } from "next";
import "./globals.css";

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
    <html lang="ja">
      <body>{children}</body>
    </html>
  );
}
