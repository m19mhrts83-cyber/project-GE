/**
 * MQ 月次まとめお知らせ（Jarvis Dashboard ホーム用）
 * trade-desk/lib/mqMonthCloseNotice.ts と同ロジック
 */

const WINDOW: [number, number] = [1, 10];

export type MqMonthCloseAckMap = Record<string, string>;

export type MqMonthCloseNotice = {
  show: boolean;
  targetMonth: string;
  title: string;
  body: string;
  hrefPath: string;
};

function tokyoParts(now = new Date()) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  return {
    y: Number(parts.find((p) => p.type === "year")?.value),
    m: Number(parts.find((p) => p.type === "month")?.value),
    d: Number(parts.find((p) => p.type === "day")?.value),
  };
}

export function previousCalendarMonth(now = new Date()): string {
  const { y, m } = tokyoParts(now);
  const dt = new Date(Date.UTC(y, m - 2, 1));
  return `${dt.getUTCFullYear()}-${String(dt.getUTCMonth() + 1).padStart(2, "0")}`;
}

export function isMqMonthCloseWindow(now = new Date()): boolean {
  const { d } = tokyoParts(now);
  return d >= WINDOW[0] && d <= WINDOW[1];
}

export function parseMqMonthCloseAck(raw: unknown): MqMonthCloseAckMap {
  if (!raw || typeof raw !== "object") return {};
  const acked = (raw as { acked?: unknown }).acked;
  if (!acked || typeof acked !== "object") return {};
  const out: MqMonthCloseAckMap = {};
  for (const [k, v] of Object.entries(acked as Record<string, unknown>)) {
    if (/^\d{4}-\d{2}$/.test(k) && typeof v === "string") out[k] = v;
  }
  return out;
}

export function mqMonthCloseNotice(
  opts: {
    acked?: MqMonthCloseAckMap;
    hasFacts?: boolean;
    now?: Date;
  } = {}
): MqMonthCloseNotice {
  const now = opts.now ?? new Date();
  const targetMonth = previousCalendarMonth(now);
  const show = isMqMonthCloseWindow(now) && !opts.acked?.[targetMonth];
  return {
    show,
    targetMonth,
    title: `MQ会計評価 — ${targetMonth} をまとめる`,
    body: opts.hasFacts
      ? `${targetMonth} の実績が入っています。KURASHIFT の MQ会計評価でまとめましょう。`
      : `${targetMonth} 分のデータが出揃う頃です。MQ会計評価で確認・まとめを。`,
    hrefPath: `/mq?grain=month&a=${encodeURIComponent(targetMonth)}&mode=aa`,
  };
}
