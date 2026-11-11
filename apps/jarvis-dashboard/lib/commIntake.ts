import type { SupabaseClient } from "@supabase/supabase-js";

/**
 * 台帳の受付窓口（POST /api/comm-intake）。ボットが直接登録する。
 * - 鍵は人ごと（COMM_INTAKE_KEYS = "grok:<鍵>,…"。復旧窓口と同じ作りで、検証は route が jobRecovery の actorForKey を使う）
 * - 形式検査・本文の大きさ上限・1分あたりの回数上限
 * - 重複（同じ bot_item_id）は受け付け済みとして成功を返す（冪等）
 * - ボットは読めない（応答は受け付けた件数と id だけ）
 * 仕様: docs/コミュニケーション台帳_受付窓口_仕様_20261111.md
 */

export const INTAKE_KINDS = ["partner", "property", "inquiry", "self", "agent", "skim"] as const;
export const MAX_BODY_BYTES = 64 * 1024;
export const MAX_ITEMS = 20;
export const PER_MINUTE = 30;
const ID_RE = /^[A-Za-z0-9._:\-]{1,128}$/;
/** 種類の印（任意）。例: daily_report／property_research／repair_vendor／dev_card。台帳で「やること」にするかの判断に使う。 */
const TOPIC_RE = /^[a-z0-9_]{1,40}$/;

export type IntakeItem = {
  bot_item_id: string;
  payload: {
    kind: string;
    occurred_at: string;
    title: string;
    summary: string;
    refs: Record<string, unknown>;
    source: string;
    topic?: string;
    needs_action?: boolean;
  };
};

function str(v: unknown): string {
  return typeof v === "string" ? v.trim() : "";
}

/** 1件の形式検査。bot は鍵から決まる送り手と一致しなければならない（省略可）。 */
export function validateItem(
  input: unknown,
  actor: string,
  now = new Date(),
): { ok: true; value: IntakeItem } | { ok: false; error: string } {
  if (!input || typeof input !== "object" || Array.isArray(input)) return { ok: false, error: "item must be an object" };
  const o = input as Record<string, unknown>;
  const bot = str(o.bot);
  if (bot && bot.toLowerCase() !== actor) return { ok: false, error: "bot does not match the key" };
  const id = str(o.bot_item_id);
  if (!ID_RE.test(id)) return { ok: false, error: "bot_item_id must be 1-128 chars of [A-Za-z0-9._:-]" };
  const kind = str(o.kind).toLowerCase();
  if (!(INTAKE_KINDS as readonly string[]).includes(kind)) return { ok: false, error: `kind must be one of ${INTAKE_KINDS.join("/")}` };
  const occ = str(o.occurred_at);
  const t = Date.parse(occ);
  if (!occ || Number.isNaN(t)) return { ok: false, error: "occurred_at must be ISO 8601" };
  if (t > now.getTime() + 24 * 3600_000) return { ok: false, error: "occurred_at is in the future" };
  if (t < now.getTime() - 400 * 24 * 3600_000) return { ok: false, error: "occurred_at is too old" };
  const title = str(o.title);
  if (!title || title.length > 300) return { ok: false, error: "title is required (max 300)" };
  const summary = typeof o.summary === "string" ? o.summary : "";
  if (summary.length > 4000) return { ok: false, error: "summary too long (max 4000)" };
  const refs = o.refs ?? {};
  if (typeof refs !== "object" || Array.isArray(refs)) return { ok: false, error: "refs must be an object" };
  if (JSON.stringify(refs).length > 4096) return { ok: false, error: "refs too large (max 4KB)" };
  const source = str(o.source);
  if (source.length > 80) return { ok: false, error: "source too long (max 80)" };
  const topic = str(o.topic).toLowerCase();
  if (topic && !TOPIC_RE.test(topic)) return { ok: false, error: "topic must be 1-40 chars of [a-z0-9_]" };
  if (o.needs_action !== undefined && typeof o.needs_action !== "boolean") {
    return { ok: false, error: "needs_action must be true/false" };
  }
  return {
    ok: true,
    value: {
      bot_item_id: id,
      payload: {
        kind,
        occurred_at: new Date(t).toISOString(),
        title,
        summary,
        refs: refs as Record<string, unknown>,
        source,
        ...(topic ? { topic } : {}),
        ...(typeof o.needs_action === "boolean" ? { needs_action: o.needs_action } : {}),
      },
    },
  };
}

/** 本文（1件 or {items:[…]}）→ 検査済みの一覧。1件でも崩れていれば全体を断る（部分受付をしない）。 */
export function validateBody(
  body: unknown,
  actor: string,
  now = new Date(),
): { ok: true; items: IntakeItem[] } | { ok: false; error: string; index?: number } {
  const list =
    body && typeof body === "object" && !Array.isArray(body) && Array.isArray((body as { items?: unknown }).items)
      ? ((body as { items: unknown[] }).items)
      : [body];
  if (list.length === 0) return { ok: false, error: "no items" };
  if (list.length > MAX_ITEMS) return { ok: false, error: `too many items (max ${MAX_ITEMS})` };
  const out: IntakeItem[] = [];
  const seen = new Set<string>();
  for (let i = 0; i < list.length; i++) {
    const v = validateItem(list[i], actor, now);
    if (!v.ok) return { ok: false, error: v.error, index: i };
    if (!seen.has(v.value.bot_item_id)) out.push(v.value);
    seen.add(v.value.bot_item_id);
  }
  return { ok: true, items: out };
}

/** 直近1分に受け付けた件数（DB で数えるのでサーバーが複数でも効く）。 */
export async function recentCount(supabase: SupabaseClient, actor: string, now = new Date()): Promise<number> {
  const since = new Date(now.getTime() - 60_000).toISOString();
  const { count, error } = await supabase
    .from("comm_intake")
    .select("id", { count: "exact", head: true })
    .eq("source_bot", actor)
    .gte("received_at", since);
  if (error) throw new Error(`intake_count:${error.message}`);
  return count || 0;
}

/** 受付の表に入れる。既にある bot_item_id は入れずに既存の id を返す（冪等）。 */
export async function enqueue(
  supabase: SupabaseClient,
  actor: string,
  items: IntakeItem[],
): Promise<{ accepted: number; created: number; ids: string[] }> {
  const rows = items.map((x) => ({ source_bot: actor, bot_item_id: x.bot_item_id, payload: x.payload }));
  const ins = await supabase
    .from("comm_intake")
    .upsert(rows, { onConflict: "source_bot,bot_item_id", ignoreDuplicates: true })
    .select("id");
  if (ins.error) throw new Error(`intake_insert:${ins.error.message}`);
  const got = await supabase
    .from("comm_intake")
    .select("id,bot_item_id")
    .eq("source_bot", actor)
    .in("bot_item_id", items.map((x) => x.bot_item_id));
  if (got.error) throw new Error(`intake_lookup:${got.error.message}`);
  const byId = new Map((got.data || []).map((r) => [String(r.bot_item_id), String(r.id)]));
  return {
    accepted: items.length,
    created: (ins.data || []).length,
    ids: items.map((x) => byId.get(x.bot_item_id) || "").filter(Boolean),
  };
}
