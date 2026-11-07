import type { Metadata, Viewport } from "next";
import "./globals.css";
import "./theme-kurashift.css";

export const metadata: Metadata = {
  title: "KURASHIFT｜クラシフト",
  description: "暮らしを整え、資産を動かす — ライフプラン軌道の資産運用HQ",
  applicationName: "KURASHIFT",
};

export const viewport: Viewport = {
  themeColor: "#13302a",
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
