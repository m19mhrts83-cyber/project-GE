// 改善履歴（2026-11-11 松野さん）。会員の声を受けて直したことを新しい順に返す。
// 画面に渡すのは日付・直したこと・説明・きっかけだけ（行の id や表示フラグは出さない）。
export type ChangeLogRow = { released_on?: unknown; title?: unknown; body?: unknown; trigger?: unknown };
const s = (v: unknown, n: number) => String(v ?? '').slice(0, n);
export function publicChangeLog(rows: ChangeLogRow[]) {
  return (Array.isArray(rows) ? rows : []).slice(0, 200).map(r => ({
    released_on: /^\d{4}-\d{2}-\d{2}$/.test(String(r.released_on ?? '')) ? String(r.released_on) : '',
    title: s(r.title, 120), body: s(r.body, 600), trigger: s(r.trigger, 200),
  })).filter(r => r.title);
}
