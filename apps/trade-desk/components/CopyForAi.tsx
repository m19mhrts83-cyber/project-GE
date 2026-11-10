"use client";

import { useState } from "react";

/** 判断ログをチャットの AI に渡す文章としてコピーする（学び・基準づくりはツールの外で） */
export default function CopyForAi({ text, count }: { text: string; count: number }) {
  const [state, setState] = useState<"idle" | "ok" | "ng">("idle");
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setState("ok");
    } catch {
      setState("ng");
    }
    window.setTimeout(() => setState("idle"), 2200);
  }
  return (
    <button type="button" className="btn" onClick={copy} disabled={count === 0}>
      {state === "ok"
        ? "コピーしました"
        : state === "ng"
          ? "コピーできませんでした"
          : `AIに渡す文章をコピー（${count}件）`}
    </button>
  );
}
