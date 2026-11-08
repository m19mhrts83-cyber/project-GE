/**
 * 判断デスクのサーバ側（service_role。ブラウザに出さない）。
 *
 * 状態を変える判断（見送る・ToDo・回答不要）は Jarvis ダッシュボードの短いリンク
 * （/api/g/ma/{action}/{id}、Slack と同じ署名 MAIL_ACTION_TOKEN）に頼む。
 * Slack カードの片付け・Gmail 既読・見送り学習まで1か所で済み、二重実装にならない。
 * 判断ログの行は DB トリガーが残すので、ここでは理由・時間・鍵を後から足す。
 */
import { createHmac } from "crypto";
import type { SupabaseClient } from "@supabase/supabase-js";
import { normalizeDecision, type DecisionInput, type Timing } from "@/lib/decisionContract";
import {
  isDeskRow,
  isLeftover,
  nextStepFor,
  orderCards,
  toCard,
  type DeskCard,
  type NextStep,
  type TriageRow,
} from "@/lib/deskCore";

export type LeftCard = DeskCard & { next: NextStep };

const COLS =
  "id,status,subject,partner,from_email,lane,kind,summary,draft_text,original_body,received_at,priority,payload";

export function dashboardBase(): string {
  return (process.env.JARVIS_DASHBOARD_URL || "https://jarvis-dashboard-amber.vercel.app").replace(/\/$/, "");
}

export async function loadDeskCards(sb: SupabaseClient, opts: { item?: string | null; limit?: number }): Promise<DeskCard[]> {
  const limit = Math.min(Math.max(opts.limit || 30, 1), 60);
  const { data, error } = await sb
    .from("triage_items")
    .select(COLS)
    .eq("status", "pending")
    .in("lane", ["partner", "general"])
    .order("received_at", { ascending: false })
    .limit(200);
  if (error) throw new Error(error.message);
  let cards = orderCards(((data || []) as TriageRow[]).filter(isDeskRow).map(toCard)).slice(0, limit);
  if (opts.item) {
    const hit = cards.find((c) => c.id === opts.item);
    if (hit) {
      cards = [hit, ...cards.filter((c) => c.id !== opts.item)];
    } else {
      const { data: one } = await sb.from("triage_items").select(COLS).eq("id", opts.item).maybeSingle();
      if (one) cards = [toCard(one as TriageRow), ...cards];
    }
  }
  return cards;
}

function maSig(id: string, action: string): string | null {
  const secret = (process.env.MAIL_ACTION_TOKEN || process.env.PROPERTY_GATE_ACTION_TOKEN || "").trim();
  if (!secret) return null;
  return createHmac("sha256", secret).update(`ma:${id}:${action}`, "utf8").digest("hex").slice(0, 10);
}

/** 残り案件（迷った・24時間たって未判断）に次の一手を付けて、古い順に */
export async function loadLeftCards(sb: SupabaseClient): Promise<LeftCard[]> {
  const all = await loadDeskCards(sb, { limit: 60 });
  const now = new Date();
  return all
    .filter((c) => isLeftover(c, now))
    .sort((a, b) => String(a.receivedAt || "").localeCompare(String(b.receivedAt || "")))
    .map((c) => ({ ...c, next: nextStepFor(c, now) }));
}

/** 3日後にもう一度出す（後で）。Jarvis の「後で」と同じ snooze_until を使う */
export async function snoozeItem(sb: SupabaseClient, id: string, days: number): Promise<boolean> {
  const { data } = await sb.from("triage_items").select("status,payload").eq("id", id).maybeSingle();
  if (!data || data.status !== "pending") return false;
  const pl = { ...((data.payload as Record<string, unknown>) || {}) };
  const until = new Date(Date.now() + days * 86400_000).toISOString();
  pl.snooze_until = until;
  pl.loopware_action = { action: "snooze", at: new Date().toISOString(), source: "loopware_desk" };
  const { error } = await sb
    .from("triage_items")
    .update({ status: "snoozed", payload: pl, updated_at: new Date().toISOString() })
    .eq("id", id);
  return !error;
}

/** 残っている理由を案件にも覚えておく（次の一手の型を選ぶため） */
export async function rememberStayReason(sb: SupabaseClient, id: string, reason: string): Promise<void> {
  const { data } = await sb.from("triage_items").select("payload").eq("id", id).maybeSingle();
  if (!data) return;
  const pl = { ...((data.payload as Record<string, unknown>) || {}) };
  pl.loopware_stay_reason = reason;
  await sb.from("triage_items").update({ payload: pl }).eq("id", id);
}

/** Jarvis の短いリンクで状態を変える（Slack と同じ処理） */
export async function applyViaDashboard(
  id: string,
  action: "skip" | "todoist" | "done",
): Promise<{ ok: boolean; message: string }> {
  const s = maSig(id, action);
  if (!s) return { ok: false, message: "MAIL_ACTION_TOKEN が loopware に設定されていません" };
  const form = new URLSearchParams({ s, intent: "confirm", via: "loopware" });
  try {
    const r = await fetch(`${dashboardBase()}/api/g/ma/${action}/${encodeURIComponent(id)}`, {
      method: "POST",
      body: form,
      headers: { "content-type": "application/x-www-form-urlencoded" },
      cache: "no-store",
    });
    const ct = r.headers.get("content-type") || "";
    if (ct.includes("application/json")) {
      const j = (await r.json()) as { ok?: boolean; message?: string };
      return { ok: Boolean(j.ok), message: String(j.message || "") };
    }
    // まだ JSON を返さない古いダッシュボード: HTML の成否で読む
    const html = await r.text();
    return { ok: r.ok && !/失敗|認証エラー|エラー/.test(html.slice(0, 600)), message: "" };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : String(e) };
  }
}

export async function alreadyLogged(sb: SupabaseClient, idemKey: string): Promise<boolean> {
  const { data } = await sb.from("owner_decisions").select("id").eq("payload->>idem_key", idemKey).limit(1).maybeSingle();
  return Boolean(data);
}

/**
 * トリガーが残した最新の行（この1分以内）に、理由・時間・鍵を足す。
 * 見つからなければ契約どおり1行を入れる（トリガーが止まっていても記録は残る）。
 */
export async function enrichTriggerRow(
  sb: SupabaseClient,
  input: DecisionInput & { idemKey: string },
): Promise<{ id: number | null; via: "trigger" | "insert" }> {
  const n = normalizeDecision(input);
  if (!n.ok) throw new Error(n.error);
  const since = new Date(Date.now() - 2 * 60_000).toISOString();
  const { data: row } = await sb
    .from("owner_decisions")
    .select("id,payload")
    .eq("target_type", "triage_item")
    .eq("target_id", input.targetId)
    .gte("decided_at", since)
    .order("decided_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (row) {
    const prev = (row.payload && typeof row.payload === "object" ? row.payload : {}) as Record<string, unknown>;
    // トリガーの値（priority・summary…）を残し、契約のキーを足す
    const merged = { ...prev, ...n.row.payload };
    await sb.from("owner_decisions").update({ payload: merged, source: n.row.source }).eq("id", row.id);
    return { id: Number(row.id), via: "trigger" };
  }
  const { data } = await sb.from("owner_decisions").insert(n.row).select("id").single();
  return { id: data ? Number(data.id) : null, via: "insert" };
}

/** 後から押された理由タグ（押さなくても進む）を、同じ判断の行に足す */
export async function addTagsByKey(
  sb: SupabaseClient,
  idemKey: string,
  patch: { reasonTags?: string[]; stayReason?: string | null; quality?: string | null; note?: string | null },
): Promise<boolean> {
  const { data: row } = await sb
    .from("owner_decisions")
    .select("id,payload,note")
    .eq("payload->>idem_key", idemKey)
    .limit(1)
    .maybeSingle();
  if (!row) return false;
  const pl = { ...((row.payload as Record<string, unknown>) || {}) };
  const probe = normalizeDecision({
    surface: "triage",
    action: "comment",
    source: "loopware",
    targetType: "triage_item",
    targetId: "-",
    reasonTags: patch.reasonTags,
    stayReason: patch.stayReason,
    quality: patch.quality,
  });
  if (probe.ok) {
    for (const k of ["reason_tags", "reason_tags_unknown", "stay_reason", "quality"]) {
      if (k in probe.row.payload) pl[k] = probe.row.payload[k];
    }
  }
  pl.tagged_at = new Date().toISOString();
  const upd: Record<string, unknown> = { payload: pl };
  if (patch.note) upd.note = String(patch.note).slice(0, 2000);
  const { error } = await sb.from("owner_decisions").update(upd).eq("id", row.id);
  return !error;
}

/** 迷ったものに印（デスクで後ろへ回す・夕方の「残り」に出す） */
export async function markHesitated(sb: SupabaseClient, id: string, timing?: Timing): Promise<void> {
  const { data } = await sb.from("triage_items").select("payload").eq("id", id).maybeSingle();
  const pl = { ...((data?.payload as Record<string, unknown>) || {}) };
  pl.loopware_hesitated_at = timing?.decided_at || new Date().toISOString();
  await sb.from("triage_items").update({ payload: pl }).eq("id", id);
}
