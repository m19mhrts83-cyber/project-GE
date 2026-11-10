// (1) AI 使用量の削減（2026-11-10）。段階公開スイッチ cost_saving が見える人の質問だけに効く。
// ・ふだんは軽いモデル（lite）で答え、詳しく調べる質問だけ今のモデル（standard）を使う
// ・同じ日（日本時間）の同じ質問だけ答えを使い回す。日付が変われば、その日までに入った投稿も含めて作り直す（11/10 松野さん）
// 判定は raimo-auth（サーバー）で行う。ブラウザからは選べない。
export type AnswerTier = 'lite' | 'standard';

// 表記ゆれだけを吸収する（全角半角・空白・末尾の「？」）。言い換えは別の質問として扱う。
export function normalizeQuery(q: string): string {
  return String(q || '').normalize('NFKC').toLowerCase().replace(/\s+/g, ' ').trim().replace(/[?？!！。．.、,]+$/u, '').trim();
}

const DEEP = /詳しく|詳細|比較|違い|手順|計算|試算|シミュレーション|それぞれ|メリット.*デメリット|事例/u;
// 長い質問・比べる/手順/計算の質問は今のモデル、それ以外は軽いモデル。
export function answerTier(q: string): AnswerTier {
  const n = normalizeQuery(q);
  return n.length > 120 || DEEP.test(n) ? 'standard' : 'lite';
}

// 「答えられない」「留意点だけ」の答えは使い回さない（次は答えられるかもしれない）。
export function cacheable(answer: string): boolean {
  const a = String(answer || '').trim();
  return a.length >= 40 && !a.includes('確証が取れない') && !a.startsWith('参考情報から読み取れる留意点');
}

export async function queryKey(q: string): Promise<string> {
  const bytes = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode('qa-cache-v1\u0000' + normalizeQuery(q))));
  return Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
}

const jstDay = (t: number) => new Date(t + 9 * 3600 * 1000).toISOString().slice(0, 10);
// 使い回せるのは「日本時間で同じ日」に作った答えだけ。
export function fresh(row: { created_at?: string } | null | undefined, now = Date.now()): boolean {
  const t = Date.parse(String(row?.created_at || ''));
  return Number.isFinite(t) && t <= now && jstDay(t) === jstDay(now);
}
