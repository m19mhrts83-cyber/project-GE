import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Prompt Share | 神大家プロンプト共有",
  description: "チャプロ代替のプロンプト共有アプリ（変数入力・コピー・外部AI動線）"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body>{children}</body>
    </html>
  );
}
