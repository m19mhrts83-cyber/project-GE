import type { Metadata, Viewport } from "next";
import "./globals.css";
import "./theme-jarvis.css";

export const metadata: Metadata = {
  title: "Jarvis Dashboard",
  description: "自分用トリアージ・状況ウォッチ",
  applicationName: "Jarvis Dashboard",
};

export const viewport: Viewport = {
  themeColor: "#0e1520",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ja" suppressHydrationWarning>
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
