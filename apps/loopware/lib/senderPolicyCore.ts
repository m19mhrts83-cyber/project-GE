/**
 * 送り手ごとの「次回から」（純粋な部品。サーバにもブラウザにも使える）。
 * 保存先は sync_meta.loopware_sender_policy。形: { entries: { "from:a@x.jp": { policy, at } } }
 *   hide      … 出さない（Slack にも判断デスクにも出さない。状態は変えない）
 *   auto_done … 出さずに自動で回答不要（Slack の投稿時に回答不要で閉じる。判断ログは source=auto_policy）
 *   always    … 毎回見る（見送り学習で自動ミュートされていても出す）
 */
export const SENDER_POLICIES = {
  hide: "出さない",
  auto_done: "出さずに自動で回答不要",
  always: "毎回見る",
} as const;
export type SenderPolicy = keyof typeof SENDER_POLICIES;
export type PolicyEntry = { policy: SenderPolicy; at: string };
export type PolicyMap = Record<string, PolicyEntry>;

export const POLICY_META_KEY = "loopware_sender_policy";

export function isPolicy(x: unknown): x is SenderPolicy {
  return typeof x === "string" && Object.prototype.hasOwnProperty.call(SENDER_POLICIES, x);
}

/** "山本 <a@x.jp>" や "A@X.jp" → "from:a@x.jp"。アドレスが取れなければ null */
export function senderKey(from: string | null | undefined): string | null {
  const s = String(from || "").trim();
  const m = s.match(/<([^>]+)>/);
  const addr = (m ? m[1] : s).trim().toLowerCase();
  return addr && addr.includes("@") ? `from:${addr}` : null;
}

/** sync_meta.value（文字列または object）→ 送り手ごとの設定。壊れていれば空 */
export function parsePolicies(raw: unknown): PolicyMap {
  let obj: unknown = raw;
  if (typeof raw === "string") {
    try {
      obj = JSON.parse(raw);
    } catch {
      return {};
    }
  }
  const entries = (obj && typeof obj === "object" ? (obj as { entries?: unknown }).entries : null) as Record<string, unknown> | null;
  const out: PolicyMap = {};
  if (entries && typeof entries === "object") {
    for (const [k, v] of Object.entries(entries)) {
      const p = v && typeof v === "object" ? (v as { policy?: unknown; at?: unknown }) : null;
      if (p && isPolicy(p.policy)) out[k] = { policy: p.policy, at: String(p.at || "") };
    }
  }
  return out;
}

export function policyOf(map: PolicyMap, from: string | null | undefined): SenderPolicy | null {
  const k = senderKey(from);
  return k && map[k] ? map[k].policy : null;
}

/** 判断デスクのカードから外す送り手か（出さない・自動で回答不要） */
export function hiddenFromDesk(map: PolicyMap, from: string | null | undefined): boolean {
  const p = policyOf(map, from);
  return p === "hide" || p === "auto_done";
}

export function withPolicy(map: PolicyMap, from: string, policy: SenderPolicy, at: string): PolicyMap {
  const k = senderKey(from);
  if (!k) return map;
  return { ...map, [k]: { policy, at } };
}
