/**
 * 従量課金の外部 API を使ってよいかの一か所の門（2026-11-20 松野さん判断）。
 *
 * 「不用意な課金を防ぎたい。従量課金にするときは一度確認してから」。
 * そのため既定はすべて止める。鍵（CURSOR_API_KEY / TAVILY_API_KEY）が Vercel にあっても、
 * Vercel の環境変数 METERED_AI_ALLOW に名前を書いた経路だけを使う（例: "cursor_cloud,tavily"）。
 * 書き足すのは松野さんが了承したときだけ。
 *
 * 例外: 判断デスクの「Gemini で作る（従量課金）」は押すたびの了承なので、この門の外（lib/geminiPaid.ts）。
 */

export type MeteredRoute = "cursor_cloud" | "tavily";

export const METERED_LABEL: Record<MeteredRoute, string> = {
  cursor_cloud: "Jarvis Cloud（Cursor・従量課金）",
  tavily: "Tavily 検索（従量課金）",
};

export function meteredAllowed(route: MeteredRoute): boolean {
  const raw = (process.env.METERED_AI_ALLOW || "").toLowerCase();
  return raw
    .split(/[\s,]+/)
    .map((s) => s.trim())
    .filter(Boolean)
    .includes(route);
}

/** 止めている理由を画面・ログに出す一文 */
export function meteredBlockedReason(route: MeteredRoute): string {
  return `${METERED_LABEL[route]}は止めています（使うときは松野さんの了承後に METERED_AI_ALLOW へ追加）`;
}
