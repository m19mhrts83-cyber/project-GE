/**
 * 松野さんの時間の使い方（週ごとの 4区分）。記録は data/timeUse.json（1週1行）。
 * 価値の3区分: steering=舵取りの判断 / clarity=分かりやすくする直し / policy=方針づくり。
 * 減らす対象: needless=聞くまでもない確認（AI の間違いのやり直しを含む）。
 * 聞くまでもない確認の割合 = needless ÷ 4区分の合計。これが下がれば良い。
 */
export type TimeUseWeek = {
  week_start: string;
  steering: number;
  clarity: number;
  policy: number;
  needless: number;
  memo: string;
  source: string;
};

export type TimeUseRow = TimeUseWeek & { ratio: number | null; total: number };

export function ratioOf(w: Pick<TimeUseWeek, "steering" | "clarity" | "policy" | "needless">): number | null {
  const t = w.steering + w.clarity + w.policy + w.needless;
  return t > 0 ? w.needless / t : null;
}

export function buildRows(weeks: TimeUseWeek[]): TimeUseRow[] {
  return [...weeks]
    .sort((a, b) => a.week_start.localeCompare(b.week_start))
    .map((w) => ({ ...w, ratio: ratioOf(w), total: w.steering + w.clarity + w.policy + w.needless }));
}

/** 月曜始まりの週の開始日（YYYY-MM-DD, JST 前提で日付だけ扱う） */
export function weekStartOf(d: Date): string {
  const jst = new Date(d.getTime() + 9 * 3600 * 1000);
  const dow = (jst.getUTCDay() + 6) % 7;
  jst.setUTCDate(jst.getUTCDate() - dow);
  return jst.toISOString().slice(0, 10);
}
