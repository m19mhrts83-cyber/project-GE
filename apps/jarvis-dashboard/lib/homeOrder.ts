/** ホームのカードの並び（端末ごとに cookie で保存）。サーバーとクライアントの両方で使う */

export const HOME_ORDER_COOKIE = "jarvis_home_order";

/** 並べ替えできるカードの初期の並び。上の「いまやること」帯と最下部の詳細は固定 */
export const HOME_DEFAULT_ORDER = [
  "today_queue",
  "uiux",
  "maturity",
  "activity",
  "loopware",
  "partner",
  "metrics",
  "kurashift",
  "watch",
  "other",
  "openchat",
];

/** 保存された並びを今あるカードに合わせる（消えたカードは捨て、新しいカードは初期の位置に差し込む） */
export function normalizeHomeOrder(saved: string[], ids: string[], defaults: string[] = HOME_DEFAULT_ORDER): string[] {
  const known = new Set(ids);
  const out = saved.filter((x, i) => known.has(x) && saved.indexOf(x) === i);
  for (const id of ids) {
    if (out.includes(id)) continue;
    const di = defaults.indexOf(id);
    // 初期の並びで自分より前にあるカードのうち、最後に置かれているものの直後へ
    let at = 0;
    for (let k = 0; k < out.length; k++) {
      if (defaults.indexOf(out[k]) !== -1 && defaults.indexOf(out[k]) < di) at = k + 1;
    }
    out.splice(di === -1 ? out.length : at, 0, id);
  }
  return out;
}

export function parseHomeOrder(raw: string | undefined | null): string[] {
  if (!raw) return [];
  try {
    return decodeURIComponent(raw)
      .split(",")
      .map((s) => s.trim())
      .filter((s) => /^[a-z_]{1,32}$/.test(s));
  } catch {
    return [];
  }
}
