/**
 * 判断デスクのサーバ側（service_role。ブラウザに出さない）。
 *
 * 状態を変える判断（見送る・ToDo・回答不要）は Jarvis ダッシュボードの短いリンク
 * （/api/g/ma/{action}/{id}、Slack と同じ署名 MAIL_ACTION_TOKEN）に頼む。
 * Slack カードの片付け・Gmail 既読・見送り学習まで1か所で済み、二重実装にならない。
 * 判断ログの行は DB トリガーが残すので、ここでは理由・時間・鍵を後から足す。
 */
import { currentActor } from "@/lib/actor";
import { createHmac } from "crypto";
import type { SupabaseClient } from "@supabase/supabase-js";
import { loadPolicies } from "@/lib/senderPolicy";
import { hiddenFromDesk } from "@/lib/senderPolicyCore";
import { normalizeDecision, type DecisionInput, type Timing } from "@/lib/decisionContract";
import {
  DECIDED_STATUSES,
  historyNotes,
  isDeskRow,
  isLeftover,
  nextStepFor,
  orderCards,
  toCard,
  type DecidedRow,
  type DeskCard,
  type NextStep,
  type TriageRow,
} from "@/lib/deskCore";

export type LeftCard = DeskCard & { next: NextStep };

const COLS =
  "id,status,subject,partner,from_email,lane,kind,channel,summary,draft_text,original_body,received_at,priority,gmail_thread_id,account,payload";

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
    .limit(600); // 自動のお知らせを外してから絞るので多めに読む
  if (error) throw new Error(error.message);
  // 送り手ごとの「次回から」: 出さない／自動で回答不要の送り手はデスクに出さない
  const policies = await loadPolicies(sb);
  let cards = orderCards(
    ((data || []) as TriageRow[]).filter(isDeskRow).filter((r) => !hiddenFromDesk(policies, r.from_email)).map(toCard),
  ).slice(0, limit);
  if (opts.item) {
    const hit = cards.find((c) => c.id === opts.item);
    if (hit) {
      cards = [hit, ...cards.filter((c) => c.id !== opts.item)];
    } else {
      const { data: one } = await sb.from("triage_items").select(COLS).eq("id", opts.item).maybeSingle();
      if (one) cards = [toCard(one as TriageRow), ...cards];
    }
  }
  return attachHistory(sb, cards);
}

/** 同じスレッド・同じ相手の過去30日の判断（返信済み・見送り済み…）をカードに付ける */
export async function attachHistory(sb: SupabaseClient, cards: DeskCard[]): Promise<DeskCard[]> {
  const emails = Array.from(new Set(cards.map((c) => c.fromEmail.trim()).filter(Boolean)));
  const threads = Array.from(new Set(cards.map((c) => c.threadId).filter(Boolean)));
  if (!emails.length && !threads.length) return cards;
  const since = new Date(Date.now() - 30 * 86400_000).toISOString();
  const cols = "id,status,from_email,gmail_thread_id,updated_at";
  const decided: DecidedRow[] = [];
  const seen = new Set<string>();
  const take = (rows: unknown) => {
    for (const r of (rows as DecidedRow[]) || []) {
      if (!seen.has(r.id)) {
        seen.add(r.id);
        decided.push(r);
      }
    }
  };
  try {
    if (emails.length) {
      const { data } = await sb
        .from("triage_items")
        .select(cols)
        .in("status", [...DECIDED_STATUSES])
        .in("from_email", emails.slice(0, 80))
        .gte("updated_at", since)
        .limit(800);
      take(data);
    }
    if (threads.length) {
      const { data } = await sb
        .from("triage_items")
        .select(cols)
        .in("status", [...DECIDED_STATUSES])
        .in("gmail_thread_id", threads.slice(0, 80))
        .limit(400);
      take(data);
    }
  } catch {
    return cards; // 履歴が取れなくてもカードは出す
  }
  return cards.map((c) => ({ ...c, history: historyNotes(c, decided) }));
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
  const actor = await currentActor();
  if (actor === "bot") return { ok: false, message: "bot_forbidden" };
  const s = maSig(id, action);
  if (!s) return { ok: false, message: "MAIL_ACTION_TOKEN が loopware に設定されていません" };
  const form = new URLSearchParams({ s, intent: "confirm", via: "loopware", actor });
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

// ---------------------------------------------------------------- 判断デスクで返信まで（2026-11-17）
// 下書き作成・点検・送信は Jarvis ダッシュボードのサーバに頼む（Gmail の鍵・OneDrive のやり取り md・
// Mac の定額 AI の受付・Slack カードの片付けがそちらにあるため）。画面は判断デスクのまま。
// 頼むときは Slack と同じ署名（MAIL_ACTION_TOKEN）をサーバ間だけで付ける。ブラウザには出さない。

export type PastReply = { id: string; subject: string; at: string; to: string; body: string };

type SentRow = {
  id: string;
  subject?: string | null;
  draft_text?: string | null;
  from_email?: string | null;
  updated_at?: string | null;
  payload?: Record<string, unknown> | null;
};

function addrOf(raw: string | null | undefined): string {
  const s = String(raw || "").trim();
  const m = s.match(/<([^>]+)>/);
  return (m ? m[1] : s).trim().toLowerCase();
}

/**
 * この相手に過去に実際に送った返信（Gmail で送ったものだけ。回答不要の記録は入れない）。
 * 同じアドレス（受信元・送った宛先）と、パートナー名が同じものを新しい順に。
 */
export async function loadPastReplies(sb: SupabaseClient, id: string, max = 5): Promise<PastReply[]> {
  const { data: me } = await sb.from("triage_items").select("id,from_email,partner,lane").eq("id", id).maybeSingle();
  if (!me) return [];
  const addr = addrOf(me.from_email as string);
  const partner = String(me.partner || "").trim();
  const cols = "id,subject,draft_text,from_email,updated_at,payload";
  const rows: SentRow[] = [];
  const seen = new Set<string>([id]);
  const take = (d: unknown) => {
    for (const r of (d as SentRow[]) || []) {
      if (seen.has(r.id)) continue;
      seen.add(r.id);
      rows.push(r);
    }
  };
  const base = () =>
    sb.from("triage_items").select(cols).eq("status", "sent").not("payload->>gmail_sent_id", "is", null);
  const jobs: PromiseLike<{ data: unknown }>[] = [];
  if (addr && addr.includes("@")) {
    jobs.push(base().ilike("from_email", `%${addr}%`).order("updated_at", { ascending: false }).limit(10));
    jobs.push(base().ilike("payload->>sent_to", addr).order("updated_at", { ascending: false }).limit(10));
  }
  if (partner && String(me.lane || "") === "partner") {
    jobs.push(base().eq("partner", partner).order("updated_at", { ascending: false }).limit(10));
  }
  const res = await Promise.allSettled(jobs);
  for (const r of res) if (r.status === "fulfilled") take(r.value.data);
  return rows
    .map((r) => {
      const pl = (r.payload || {}) as Record<string, unknown>;
      return {
        id: r.id,
        subject: String(r.subject || "").slice(0, 160),
        at: String(pl.sent_at || r.updated_at || ""),
        to: String(pl.sent_to || addrOf(r.from_email)),
        body: String(r.draft_text || "").trim().slice(0, 3000),
      };
    })
    .filter((r) => r.body)
    .sort((a, b) => b.at.localeCompare(a.at))
    .slice(0, max);
}

export type DraftOp = "compose" | "proofread" | "revise" | "context" | "status";
/** flat = Mac の定額 AI（既定）／gemini = 従量課金（松野さんが画面で1回ごとに了承したときだけ） */
export type DraftEngine = "flat" | "gemini";

export type DraftResult = {
  ok: boolean;
  /** Mac の定額 AI がまだ作っている（少し待ってもう一度） */
  pending?: boolean;
  text?: string;
  changes?: string[];
  message?: string;
  /** やり取り md の末尾（context のとき） */
  log?: { folder?: string; notice: string; tail: string } | null;
  /** context のとき: Chatwork の返信待ちなら、送れる登録ルームと推定ルーム */
  chatwork?: { rooms: { id: string; name: string }[]; guess: string } | null;
  /** status のとき: Mac の定額 AI の係の最後の生存報告から何秒か */
  macAgeSec?: number | null;
  macAlive?: boolean;
  gemini?: boolean;
  engine?: DraftEngine;
};

async function postJson(url: string, body: unknown, timeoutMs: number): Promise<{ status: number; json: Record<string, unknown> }> {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const r = await fetch(url, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
      signal: ctl.signal,
    });
    let json: Record<string, unknown> = {};
    try {
      json = (await r.json()) as Record<string, unknown>;
    } catch {
      json = { ok: false, message: `Jarvis が JSON を返しませんでした（${r.status}）。ダッシュボードが古い版の可能性があります` };
    }
    return { status: r.status, json };
  } finally {
    clearTimeout(t);
  }
}

/** 下書き作成・誤字脱字・指示で見直し・やり取り md の読み出し（Jarvis 側 /api/g/lwdraft/{id}） */
export async function draftViaDashboard(
  id: string,
  op: DraftOp,
  args: { draft?: string; instruction?: string; engine?: DraftEngine },
): Promise<DraftResult> {
  const s = maSig(id, "lwdraft");
  if (!s) return { ok: false, message: "MAIL_ACTION_TOKEN が loopware に設定されていません" };
  try {
    const { json } = await postJson(
      `${dashboardBase()}/api/g/lwdraft/${encodeURIComponent(id)}`,
      { s, op, draft: args.draft || "", instruction: args.instruction || "", engine: args.engine || "flat" },
      op === "context" || op === "status" ? 20_000 : 80_000,
    );
    return json as DraftResult;
  } catch (e) {
    const aborted = e instanceof Error && e.name === "AbortError";
    return aborted
      ? { ok: false, pending: true, message: "Mac の定額AIで作成中です。少し待ってからもう一度押してください" }
      : { ok: false, message: e instanceof Error ? e.message : String(e) };
  }
}

/** 送信（Slack の返信と同じ処理: Gmail 送信・Slack カード片付け・Todoist を閉じる・判断ログ） */
export async function sendViaDashboard(
  id: string,
  args: {
    body: string;
    to?: string;
    account?: string;
    /** Chatwork の返信待ちで送るルーム */
    room?: string;
    openedAt?: number;
    assist?: { proofread?: number; revise?: number };
  },
): Promise<{ ok: boolean; message: string }> {
  const actor = await currentActor();
  if (actor === "bot") return { ok: false, message: "bot_forbidden" };
  const s = maSig(id, "reply");
  if (!s) return { ok: false, message: "MAIL_ACTION_TOKEN が loopware に設定されていません" };
  const form = new URLSearchParams({ s, intent: "send", via: "loopware", actor, body: args.body });
  if (args.to) form.set("to", args.to);
  if (args.account) form.set("account", args.account);
  if (args.room) form.set("room", args.room);
  if (args.openedAt) form.set("opened_at", String(args.openedAt));
  if (args.assist?.proofread) form.set("proofread", String(args.assist.proofread));
  if (args.assist?.revise) form.set("revise", String(args.assist.revise));
  try {
    const r = await fetch(`${dashboardBase()}/api/g/ma/reply/${encodeURIComponent(id)}`, {
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
    // 古いダッシュボード（HTML を返す）
    const html = await r.text();
    const ok = r.ok && /送信完了/.test(html) && !/失敗|認証エラー/.test(html.slice(0, 800));
    return { ok, message: ok ? "送信しました" : "送れませんでした（Jarvis の画面で確かめてください）" };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : String(e) };
  }
}
