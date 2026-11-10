// (3) 名簿との照合（2026-11-10）。段階公開スイッチ auto_approval が見える管理者だけ。
// 照合先は運営の「目標設定・合格状況」シート。Supabase には平文の名前を置かず、
// 会員番号と「会員番号＋名前」のハッシュだけを置く（同期は scripts/kamiooya_roster_sync.py）。
// まずは「名簿一致」を承認画面に出し、承認ボタンは人が押す（自動で承認はしない）。
export type MatchStatus = 'match' | 'number_only' | 'none' | 'duplicate' | 'missing';

export function normalizeMemberNo(v: unknown): string {
  const s = String(v ?? '').normalize('NFKC').replace(/[\s\-ー－_]/g, '').toLowerCase();
  return /^\d+$/.test(s) ? s.replace(/^0+(?=\d)/, '') : s;
}
// 名前は空白・中黒・全角半角の違いだけ吸収する（漢字の異体字やふりがなは別人扱い＝人の確認へ）。
export function normalizeName(v: unknown): string {
  return String(v ?? '').normalize('NFKC').replace(/[\s・･.]/g, '').toLowerCase();
}
export async function rosterHash(kind: 'no' | 'no_name', memberNo: unknown, name?: unknown): Promise<string> {
  const value = kind === 'no' ? normalizeMemberNo(memberNo) : normalizeMemberNo(memberNo) + '|' + normalizeName(name);
  const bytes = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode('qa-roster-v1\u0000' + kind + '\u0000' + value)));
  return Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
}

type Pending = { id: string; member_no?: unknown; name?: unknown };
// 会員番号と名前の両方が名簿と同じ → match。番号だけ同じ → number_only（なりすましの恐れ、人が確認）。
// 承認待ちの中で同じ会員番号が2人以上 → duplicate（人が確認）。番号か名前が空 → missing。
// lookup には「名簿にあるハッシュ」を問い合わせる関数を渡す（名簿全件は読まない）。
export async function matchPending(users: Pending[], lookup: (hashes: string[]) => Promise<Set<string>>): Promise<Record<string, MatchStatus>> {
  const count = new Map<string, number>();
  for (const u of users) { const n = normalizeMemberNo(u.member_no); if (n) count.set(n, (count.get(n) || 0) + 1); }
  const keyed: { id: string; no: string; pair: string }[] = [];
  const out: Record<string, MatchStatus> = {};
  for (const u of users) {
    const n = normalizeMemberNo(u.member_no), nm = normalizeName(u.name);
    if (!n || !nm) { out[u.id] = 'missing'; continue; }
    if ((count.get(n) || 0) > 1) { out[u.id] = 'duplicate'; continue; }
    keyed.push({ id: u.id, no: await rosterHash('no', n), pair: await rosterHash('no_name', n, nm) });
  }
  const found = keyed.length ? await lookup(keyed.flatMap(k => [k.no, k.pair])) : new Set<string>();
  for (const k of keyed) out[k.id] = found.has(k.pair) ? 'match' : found.has(k.no) ? 'number_only' : 'none';
  return out;
}
