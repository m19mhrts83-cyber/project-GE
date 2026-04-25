import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "神・大家さん倶楽部 Q&A",
  description: "参照ファイルを根拠に回答するQ&Aチャットボット"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body
        style={{
          margin: 0,
          fontFamily:
            'ui-sans-serif, system-ui, -apple-system, "Noto Sans JP", "Segoe UI", sans-serif',
          background: "#0b1220",
          color: "#e5e7eb"
        }}
      >
        {children}
      </body>
    </html>
  );
}

