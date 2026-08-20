/**
 * MQ 月次まとめお知らせ（両ホーム共通ロジック）
 * ウィンドウ: 翌月1〜10日 JST。対象は前暦月。
 */

import { MQ_POLICY } from "./mqPolicy";

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
  targetMonth: string; // YYYY-MM
  title: string;
  body: string;
  href: string;
  cashflowHref?: string;
  statusLabel: "取込待ち" | "自動更新済み" | "要確認" | null;
};

function tokyoParts(now = new Date()) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const y = Number(parts.find((p) => p.type === "year")?.value);
  const m = Number(parts.find((p) => p.type === "month")?.value);
  const d = Number(parts.find((p) => p.type === "day")?.value);
  return { y, m, d };
}

/** 前暦月 YYYY-MM */
export function previousCalendarMonth(now = new Date()): string {
  const { y, m } = tokyoParts(now);
  const dt = new Date(Date.UTC(y, m - 2, 1));
  const yy = dt.getUTCFullYear();
  const mm = String(dt.getUTCMonth() + 1).padStart(2, "0");
  return `${yy}-${mm}`;
}

export function isMqMonthCloseWindow(now = new Date()): boolean {
  const { d } = tokyoParts(now);
  const [from, to] = MQ_POLICY.monthCloseWindowDays;
  return d >= from && d <= to;
}

export function parseMqMonthCloseAck(raw: unknown): MqMonthCloseAckMap {
  if (!raw || typeof raw !== "object") return {};
  const o = raw as Record<string, unknown>;
  const acked = o.acked;
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
    /** 対象月に実績行があるか（任意・文言強化） */
    hasFacts?: boolean;
    autoRefresh?: MqAutoRefreshStatus | null;
    now?: Date;
  } = {}
): MqMonthCloseNotice {
  const now = opts.now ?? new Date();
  const targetMonth = previousCalendarMonth(now);
  const acked = opts.acked ?? {};
  const inWindow = isMqMonthCloseWindow(now);
  const already = Boolean(acked[targetMonth]);
  const show = inWindow && !already;

  const ar = opts.autoRefresh;
  let statusLabel: MqMonthCloseNotice["statusLabel"] = null;
  let statusLine = "";
  if (ar) {
    if (ar.ok === false) {
      statusLabel = "要確認";
      statusLine = `自動更新に失敗または未完了があります（未分類 ${ar.unmapped_total ?? "—"}）。`;
    } else if (ar.ok === true) {
      statusLabel = "自動更新済み";
      const parts = [
        `未分類 ${ar.unmapped_total ?? 0}`,
        `不動産寄せ ${ar.heuristic_total ?? 0}`,
        `手入力保護 ${ar.manual_protected ?? 0}`,
      ];
      statusLine = `自動更新済み（${parts.join("・")}）。`;
    }
  } else if (!opts.hasFacts) {
    statusLabel = "取込待ち";
  }

  const isDecemberClose = targetMonth.endsWith("-12");
  const bodyBase = opts.hasFacts
    ? `${targetMonth} の実績が入っています。資金繰り表（帳簿）・MQ会計表・現金橋・軽量B/Sをまとめて確認しましょう。`
    : `${targetMonth} 分のデータが出揃う頃です。Zaim取込や手入力のうえ、資金繰り表と MQ会計評価でまとめましょう。`;
  const yearendLine = isDecemberClose
    ? " 12月は期末利息・税金支払の入力も資金繰り表から行えます。"
    : "";

  return {
    show,
    targetMonth,
    title: `MQ会計評価 — ${targetMonth} をまとめる`,
    body: `${statusLine ? `${bodyBase} ${statusLine}` : bodyBase}${yearendLine}`,
    href: `/mq?grain=month&a=${encodeURIComponent(targetMonth)}&b=${encodeURIComponent(targetMonth)}&mode=aa`,
    cashflowHref: `/mq?view=cashflow&grain=year&line=realestate&entity=corporate&a=${encodeURIComponent(targetMonth.slice(0, 4))}`,
    statusLabel,
  };
}
