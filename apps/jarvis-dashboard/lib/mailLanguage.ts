/** 英語メール判定（和訳表示用。送信本文は置き換えない） */

const KANA_KANJI = /[\u3040-\u30ff\u4e00-\u9fff]/g;
const LATIN = /[A-Za-z]/g;

export function looksEnglish(text: string | null | undefined): boolean {
  const t = String(text || "").trim();
  if (t.length < 40) return false;
  const letters = t.match(LATIN)?.length || 0;
  const jp = t.match(KANA_KANJI)?.length || 0;
  if (jp >= 12) return false;
  return letters >= 80 && letters > jp * 4;
}
