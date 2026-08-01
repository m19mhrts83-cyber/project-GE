"use client";

import { useState } from "react";

export default function CopyPathButton({
  path,
  label = "パスをコピー",
}: {
  path: string;
  label?: string;
}) {
  const [ok, setOk] = useState(false);
  return (
    <button
      type="button"
      className="copy-path-btn"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(path);
          setOk(true);
          setTimeout(() => setOk(false), 2000);
        } catch {
          setOk(false);
        }
      }}
    >
      {ok ? "コピーしました" : label}
    </button>
  );
}
