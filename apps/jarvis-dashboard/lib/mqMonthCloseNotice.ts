/**
 * MQ 月次まとめお知らせ（Jarvis Dashboard ホーム用）
 * trade-desk/lib/mqMonthCloseNotice.ts と同ロジック
 */

const WINDOW: [number, number] = [1, 10];

export type MqMonthCloseAckMap = Record<string, string>;

export type MqAutoRefreshStatus = {
  ok?: boolean;
  cycle_month?: string;
  unmapped_total?: number;
  heuristic_total?: number;
  manual_protected?: number;
  at?: string;
};

export type MqMonthCloseNotice = {
  show: boolean;
  targetMonth: string;
  title: string;
  body: string;
  hrefPath: string;
  statusLabel: "取込待ち" | "自動更新済み" | "要確認" | null;
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

export function parseMqAutoRefresh(raw: unknown): MqAutoRefreshStatus | null {
  if (!raw || typeof raw !== "object") return null;
  return raw as MqAutoRefreshStatus;
}

export function mqMonthCloseNotice(
  opts: {
    acked?: MqMonthCloseAckMap;
    hasFacts?: boolean;
    autoRefresh?: MqAutoRefreshStatus | null;
    now?: Date;
  } = {}
): MqMonthCloseNotice {
  const now = opts.now ?? new Date();
  const targetMonth = previousCalendarMonth(now);
  const show = isMqMonthCloseWindow(now) && !opts.acked?.[targetMonth];

  const ar = opts.autoRefresh;
  let statusLabel: MqMonthCloseNotice["statusLabel"] = null;
  let statusLine = "";
  if (ar) {
    if (ar.ok === false) {
      statusLabel = "要確認";
      statusLine = `自動更新に失敗または未完了があります（未分類 ${ar.unmapped_total ?? "—"}）。`;
    } else if (ar.ok === true) {
      statusLabel = "自動更新済み";
      statusLine = `自動更新済み（未分類 ${ar.unmapped_total ?? 0}・不動産寄せ ${ar.heuristic_total ?? 0}・手入力保護 ${ar.manual_protected ?? 0}）。`;
    }
  } else if (!opts.hasFacts) {
    statusLabel = "取込待ち";
  }

  const bodyBase = opts.hasFacts
    ? `${targetMonth} の実績が入っています。KURASHIFT の MQ会計評価でまとめましょう。`
    : `${targetMonth} 分のデータが出揃う頃です。MQ会計評価で確認・まとめを。`;

  return {
    show,
    targetMonth,
    title: `MQ会計評価 — ${targetMonth} をまとめる`,
    body: statusLine ? `${bodyBase} ${statusLine}` : bodyBase,
    hrefPath: `/mq?grain=month&a=${encodeURIComponent(targetMonth)}&mode=aa`,
    statusLabel,
  };
}
