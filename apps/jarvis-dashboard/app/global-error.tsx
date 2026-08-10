"use client";

import { useEffect } from "react";

function isChunkLoadError(error: Error): boolean {
  const msg = `${error?.name || ""} ${error?.message || ""}`;
  return (
    /ChunkLoadError/i.test(msg) ||
    /Loading chunk [\d]+ failed/i.test(msg) ||
    /Failed to fetch dynamically imported module/i.test(msg) ||
    /Importing a module script failed/i.test(msg)
  );
}

const RELOAD_KEY = "jarvis_chunk_reload_once";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    if (!isChunkLoadError(error)) return;
    try {
      if (sessionStorage.getItem(RELOAD_KEY) === "1") return;
      sessionStorage.setItem(RELOAD_KEY, "1");
      window.location.reload();
    } catch {
      /* ignore */
    }
  }, [error]);

  return (
    <html lang="ja">
      <body
        style={{
          margin: 0,
          fontFamily: "system-ui, sans-serif",
          padding: "2rem",
        }}
      >
        <h2 style={{ fontSize: "1.1rem" }}>アプリの読み込みで問題が起きました</h2>
        <p style={{ color: "#666", fontSize: "0.9rem" }}>
          デプロイ直後の古いキャッシュが原因のことがあります。再読み込みを試してください。
        </p>
        {error?.message ? (
          <pre
            style={{
              whiteSpace: "pre-wrap",
              fontSize: "0.75rem",
              background: "#f5f5f5",
              padding: "0.75rem",
              borderRadius: 6,
            }}
          >
            {error.message}
          </pre>
        ) : null}
        <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem" }}>
          <button
            type="button"
            onClick={() => {
              try {
                sessionStorage.removeItem(RELOAD_KEY);
              } catch {
                /* ignore */
              }
              window.location.reload();
            }}
          >
            再読み込み
          </button>
          <button type="button" onClick={() => reset()}>
            再試行
          </button>
        </div>
      </body>
    </html>
  );
}
