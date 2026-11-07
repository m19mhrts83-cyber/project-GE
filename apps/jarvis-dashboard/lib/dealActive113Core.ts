/**
 * 113 物件買進め確認係 — #deal-active「どうしますか？」ボタンの中核（純関数）。
 *
 * value: d113:{continue|hold|pass|done}:{deal_id}:{sig10}
 * 署名は Python 側 scripts/kurashift_deal_active_113.py と同じ順の秘密で HMAC-SHA256。
 * ここは import 先を crypto だけにして、node --test から直接読めるようにしている。
 */
import { createHmac, timingSafeEqual } from "node:crypto";

export type D113Action = "continue" | "hold" | "pass" | "done";

export const D113_ACTIONS: D113Action[] = ["continue", "hold", "pass", "done"];

export const D113_LABEL: Record<D113Action, string> = {
  continue: "続ける（あと14日）",
  hold: "保留（30日後に再確認）",
  pass: "見送り",
  done: "完了（外す）",
};

export const D113_ICON: Record<D113Action, string> = {
  continue: "▶️",
  hold: "⏸️",
  pass: "🗑️",
  done: "✅",
};

/** 署名に使う秘密の候補（先頭で署名、全部で検証）。Python の ACTION_SECRET_NAMES と同じ順。 */
export const D113_SECRET_NAMES = [
  "DEAL_ACTIVE_113_ACTION_TOKEN",
  "PROPERTY_GATE_ACTION_TOKEN",
] as const;

export function d113Secrets(env: Record<string, string | undefined> = process.env): string[] {
  const out: string[] = [];
  for (const name of D113_SECRET_NAMES) {
    const s = (env[name] || "").trim();
    if (s && !out.includes(s)) out.push(s);
  }
  return out;
}

export function d113SigWith(secret: string, action: D113Action, dealId: string): string {
  return createHmac("sha256", secret)
    .update(`d113:${action}:${dealId}`, "utf8")
    .digest("hex")
    .slice(0, 10);
}

export function d113ButtonValue(
  action: D113Action,
  dealId: string,
  env: Record<string, string | undefined> = process.env,
): string {
  const secret = d113Secrets(env)[0] || "";
  return `d113:${action}:${dealId}:${secret ? d113SigWith(secret, action, dealId) : ""}`;
}

export function parseD113ButtonValue(
  value: string,
  env: Record<string, string | undefined> = process.env,
): { action: D113Action; dealId: string } | null {
  const m = String(value || "")
    .trim()
    .match(/^d113:(continue|hold|pass|done):([A-Za-z0-9-]{1,64}):([a-f0-9]{10})$/);
  if (!m) return null;
  const action = m[1] as D113Action;
  const dealId = m[2];
  const got = Buffer.from(m[3]);
  for (const secret of d113Secrets(env)) {
    const want = Buffer.from(d113SigWith(secret, action, dealId));
    if (want.length === got.length && timingSafeEqual(want, got)) {
      return { action, dealId };
    }
  }
  return null;
}

export type D113State = {
  channel?: string;
  ts?: string;
  state?: "active" | "needs_check" | "hold" | "dormant" | "closed";
  last_moved_at?: string;
  next_check_at?: string;
  asked_count?: number;
  closed_at?: string | null;
  closed_reason?: D113Action | null;
  decided_at?: string;
  [k: string]: unknown;
};

function addDays(day: string, n: number): string {
  const d = new Date(`${day}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

/** ボタン1回ぶんの状態遷移。today は JST の YYYY-MM-DD。 */
export function nextD113State(st: D113State, action: D113Action, today: string): D113State {
  const s: D113State = { ...st, decided_at: today, asked_count: 0 };
  if (action === "continue") {
    s.state = "active";
    s.next_check_at = addDays(today, 14);
  } else if (action === "hold") {
    s.state = "hold";
    s.next_check_at = addDays(today, 30);
  } else {
    s.state = "closed";
    s.closed_at = today;
    s.closed_reason = action;
  }
  return s;
}

/** 押した案件の行（block_id = d113_{deal_id}）だけ、ボタンを結果1行に置き換える。 */
export function replaceDecidedRow(
  blocks: Array<Record<string, unknown>>,
  dealId: string,
  action: D113Action,
  who: string,
): Array<Record<string, unknown>> {
  const id = `d113_${dealId}`;
  return blocks.map((b) =>
    b.block_id === id
      ? {
          type: "context",
          block_id: id,
          elements: [
            {
              type: "mrkdwn",
              text: `${D113_ICON[action]} ${D113_LABEL[action]}${who ? `（<@${who}>）` : ""}`,
            },
          ],
        }
      : b,
  );
}

export function jstToday(now: Date = new Date()): string {
  return new Date(now.getTime() + 9 * 3600 * 1000).toISOString().slice(0, 10);
}
