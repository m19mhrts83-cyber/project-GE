/** Quiet Edge Phase 3 — Journal 欠落・異常検知と問い生成 */

export type JournalDailyRow = {
  recorded_at: string;
  excerpt: string;
  char_count: number;
  source: string;
};

export type ContextNoteRow = {
  id: number;
  recorded_at: string;
  trigger: string;
  prompt: string;
  answer: string;
  source: string;
  created_at: string;
};

export type SnoreLite = {
  recorded_at: string;
  score: number;
  count: number | null;
};

export type VitalLite = {
  recorded_at: string;
  metric: string;
  value: number;
};

export type QuietEdgeAsk = {
  recorded_at: string;
  trigger: string;
  prompt: string;
  reason: string;
};

function ymdJst(d: Date): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(d);
}

function addDaysYmd(ymd: string, delta: number): string {
  const [y, m, d] = ymd.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  dt.setUTCDate(dt.getUTCDate() + delta);
  return dt.toISOString().slice(0, 10);
}

/** 直近 N 日で Journal 欠落・いびき急変を拾い、未回答の問いを返す */
export function buildQuietEdgeAsks(input: {
  journals: JournalDailyRow[];
  notes: ContextNoteRow[];
  snore: SnoreLite[];
  vitals?: VitalLite[];
  windowDays?: number;
  maxAsks?: number;
}): QuietEdgeAsk[] {
  const windowDays = input.windowDays ?? 14;
  const maxAsks = input.maxAsks ?? 5;
  const today = ymdJst(new Date());
  const start = addDaysYmd(today, -(windowDays - 1));

  const journalByDay = new Map(
    input.journals.map((j) => [j.recorded_at, j] as const),
  );
  const answered = new Set(
    input.notes
      .filter((n) => n.answer && n.answer.trim().length > 0)
      .map((n) => `${n.recorded_at}|${n.trigger}`),
  );

  const snoreSorted = [...input.snore]
    .filter((s) => s.recorded_at >= start && s.recorded_at <= today)
    .sort((a, b) => a.recorded_at.localeCompare(b.recorded_at));

  const asks: QuietEdgeAsk[] = [];

  // 1) Journal 欠落（いびき記録がある日を優先）
  const snoreDays = new Set(snoreSorted.map((s) => s.recorded_at));
  for (let i = 0; i < windowDays; i++) {
    const d = addDaysYmd(start, i);
    if (d >= today) continue; // 今日は書いている最中かも
    const j = journalByDay.get(d);
    const thin = !j || !j.excerpt.trim() || j.char_count < 40;
    if (!thin) continue;
    const trigger = "missing_journal";
    if (answered.has(`${d}|${trigger}`)) continue;
    const hasSnore = snoreDays.has(d);
    asks.push({
      recorded_at: d,
      trigger,
      reason: hasSnore
        ? "いびき記録あり・Journal 薄い／なし"
        : "Journal が無い／極端に短い",
      prompt: hasSnore
        ? `${d} はいびき記録がありますが Journal が薄いです。その夜〜朝、何がありましたか？（飲酒・残業・鼻詰まり・旅行など短くでOK）`
        : `${d} の Journal が見つかりません。覚えていれば、その日の睡眠まわりで何がありましたか？`,
    });
  }

  // 2) いびきスコア急変（前日比 +15 以上、または回数 1.6 倍）
  for (let i = 1; i < snoreSorted.length; i++) {
    const prev = snoreSorted[i - 1];
    const cur = snoreSorted[i];
    const scoreJump = Number(cur.score) - Number(prev.score) >= 15;
    const countJump =
      prev.count != null &&
      cur.count != null &&
      prev.count > 0 &&
      cur.count / prev.count >= 1.6 &&
      cur.count - prev.count >= 20;
    if (!scoreJump && !countJump) continue;
    const trigger = "snore_spike";
    if (answered.has(`${cur.recorded_at}|${trigger}`)) continue;
    asks.push({
      recorded_at: cur.recorded_at,
      trigger,
      reason: scoreJump
        ? `スコア ${Number(prev.score).toFixed(1)}→${Number(cur.score).toFixed(1)}`
        : `回数 ${prev.count}→${cur.count}`,
      prompt: `${cur.recorded_at} のいびきが前日より悪化しています（${
        scoreJump
          ? `スコア ${Number(prev.score).toFixed(1)}→${Number(cur.score).toFixed(1)}`
          : `回数 ${prev.count}→${cur.count}`
      }）。その夜、何がありましたか？`,
    });
  }

  // 優先: spike → missing with snore → missing
  const rank = (a: QuietEdgeAsk) =>
    a.trigger === "snore_spike" ? 0 : a.reason.includes("いびき") ? 1 : 2;
  asks.sort((a, b) => {
    const r = rank(a) - rank(b);
    if (r !== 0) return r;
    return b.recorded_at.localeCompare(a.recorded_at);
  });

  // 同日は1つに抑制
  const seenDay = new Set<string>();
  const out: QuietEdgeAsk[] = [];
  for (const a of asks) {
    if (seenDay.has(a.recorded_at)) continue;
    seenDay.add(a.recorded_at);
    out.push(a);
    if (out.length >= maxAsks) break;
  }
  return out;
}
