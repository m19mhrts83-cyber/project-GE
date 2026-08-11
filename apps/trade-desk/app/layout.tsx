import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Trade Desk",
  description: "Jarvis 株・資産デスク（ダッシュボードとは別アプリ）",
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
