import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "KURASHIFT",
  description: "暮らしを整え、資産を動かす — ライフプラン軌道の資産運用HQ",
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
