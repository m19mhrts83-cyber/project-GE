/**
 * 松野さんの時間の使い方（週ごとの 判断／直し／方針づくり）。
 * 記録は data/timeUse.json（1週1行）。判断の比率 = 判断 ÷ (判断 + 直し)。方針づくりは別枠で比率に入れない。
 */
export type TimeUseWeek = {
  week_start: string;
  decisions: number;
  fixes: number;
  policy: number;
  memo: string;
  source: string;
};

export type TimeUseRow = TimeUseWeek & { ratio: number | null };

export function ratioOf(decisions: number, fixes: number): number | null {
  const t = decisions + fixes;
  return t > 0 ? decisions / t : null;
}

export function buildRows(weeks: TimeUseWeek[]): TimeUseRow[] {
  return [...weeks]
    .sort((a, b) => a.week_start.localeCompare(b.week_start))
    .map((w) => ({ ...w, ratio: ratioOf(w.decisions, w.fixes) }));
}

/** 月曜始まりの週の開始日（YYYY-MM-DD, JST 前提で日付だけ扱う） */
export function weekStartOf(d: Date): string {
  const jst = new Date(d.getTime() + 9 * 3600 * 1000);
  const dow = (jst.getUTCDay() + 6) % 7;
  jst.setUTCDate(jst.getUTCDate() - dow);
  return jst.toISOString().slice(0, 10);
}
