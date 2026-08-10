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

export default function Error({
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
    <div
      style={{
        padding: "2rem",
        maxWidth: 520,
        margin: "2rem auto",
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <h2 style={{ fontSize: "1.1rem" }}>画面の読み込みで問題が起きました</h2>
      <p style={{ color: "#666", fontSize: "0.9rem" }}>
        デプロイ直後の古いキャッシュが原因のことがあります。再読み込みで直ることが多いです。
      </p>
      {error?.message ? (
        <pre
          style={{
            whiteSpace: "pre-wrap",
            fontSize: "0.75rem",
            background: "#f5f5f5",
            padding: "0.75rem",
            borderRadius: 6,
            overflow: "auto",
          }}
        >
          {error.message}
          {error.digest ? `\ndigest: ${error.digest}` : ""}
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
          style={{
            padding: "0.5rem 1rem",
            cursor: "pointer",
          }}
        >
          再読み込み
        </button>
        <button
          type="button"
          onClick={() => reset()}
          style={{
            padding: "0.5rem 1rem",
            cursor: "pointer",
          }}
        >
          再試行
        </button>
      </div>
    </div>
  );
}
