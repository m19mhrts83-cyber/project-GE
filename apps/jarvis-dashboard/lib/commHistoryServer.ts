import { createServiceClient } from "@/lib/supabase/admin";
import {
  formatHistoryBlock,
  matchPartyIds,
  normFolder,
  summarizeByParty,
  type CommItem,
  type CommParty,
  type PartySummary,
} from "@/lib/commHistory";

/**
 * コミュニケーション台帳（comm_items / comm_parties）の読み出し。
 * 個人情報の表なので service_role でサーバ側だけ読む（画面はログイン必須）。書き込みはしない。
 */

const ITEM_COLS = "id,party_id,channel,direction,occurred_at,subject,summary,body_text";

async function loadParties(sb: NonNullable<ReturnType<typeof createServiceClient>>): Promise<CommParty[]> {
  const { data } = await sb
    .from("comm_parties")
    .select("party_id,name,partner_folder,emails,email_domains")
    .eq("active", true);
  return (data || []) as CommParty[];
}

export async function loadPartySummaries(opts: { scan?: number; perParty?: number } = {}): Promise<
  { ok: true; parties: PartySummary[] } | { ok: false; error: string }
> {
  const sb = createServiceClient();
  if (!sb) return { ok: false, error: "Supabase が未設定です" };
  const [parties, items] = await Promise.all([
    loadParties(sb),
    sb
      .from("comm_items")
      .select("id,party_id,channel,direction,occurred_at,subject,summary")
      .eq("ingest_status", "ready")
      .eq("category", "partner")
      .not("party_id", "is", null)
      .order("occurred_at", { ascending: false })
      .limit(opts.scan ?? 1500),
  ]);
  if (items.error) return { ok: false, error: items.error.message };
  return { ok: true, parties: summarizeByParty(parties, (items.data || []) as CommItem[], new Date(), opts.perParty ?? 3) };
}

export type PendingReply = {
  id: string;
  subject: string | null;
  summary: string | null;
  received_at: string | null;
  draft_text: string | null;
  channel: string | null;
};

export async function loadPartyTimeline(
  name: string,
  limit = 40,
): Promise<
  { ok: true; party: CommParty | null; items: CommItem[]; pending: PendingReply[] } | { ok: false; error: string }
> {
  const sb = createServiceClient();
  if (!sb) return { ok: false, error: "Supabase が未設定です" };
  const parties = await loadParties(sb);
  const same = parties.filter((p) => p.name === name);
  if (same.length === 0) return { ok: true, party: null, items: [], pending: [] };
  // 返信待ち（判断デスクのカードと同じ triage_items）。フォルダは P 付き・無しの両方で拾う
  const folders = new Set<string>();
  for (const p of same) {
    const f = normFolder(p.partner_folder);
    if (f) {
      folders.add(f);
      folders.add(`P${f}`);
    }
  }
  const pendingQ = sb
    .from("triage_items")
    .select("id,subject,summary,received_at,draft_text,channel")
    .eq("status", "pending")
    .eq("lane", "partner")
    .neq("kind", "activity")
    .order("received_at", { ascending: false })
    .limit(10);
  const pendingRes = folders.size
    ? await pendingQ.in("folder", [...folders])
    : await pendingQ.eq("partner", name);
  const { data, error } = await sb
    .from("comm_items")
    .select(ITEM_COLS)
    .in(
      "party_id",
      same.map((p) => p.party_id),
    )
    .eq("ingest_status", "ready")
    .order("occurred_at", { ascending: false })
    .limit(limit);
  if (error) return { ok: false, error: error.message };
  const party = same.find((p) => /^P\d/.test(p.partner_folder || "")) || same[0];
  return { ok: true, party, items: (data || []) as CommItem[], pending: (pendingRes.data || []) as PendingReply[] };
}

/**
 * 返信下書きの背景（判断デスク /api/g/lwdraft から使う）。
 * retrieveYoritooriForAsk と同じ形で返すので、呼び出し側は台帳が空なら md へ切り替えるだけ。
 */
export async function commHistoryForReply(q: {
  folder?: string | null;
  partner?: string | null;
  email?: string | null;
  recent?: number;
  mine?: number;
}): Promise<{ ok: boolean; promptBlock: string; notice: string; path?: string; chars?: number }> {
  const sb = createServiceClient();
  if (!sb) return { ok: false, promptBlock: "", notice: "台帳: Supabase 未設定" };
  try {
    const parties = await loadParties(sb);
    const ids = matchPartyIds(parties, q);
    if (ids.length === 0) return { ok: false, promptBlock: "", notice: "台帳: 相手を特定できず" };
    const name = parties.find((p) => p.party_id === ids[0])?.name || String(q.partner || "相手");
    const base = () =>
      sb.from("comm_items").select(ITEM_COLS).in("party_id", ids).eq("ingest_status", "ready").order("occurred_at", { ascending: false });
    const [recent, mine] = await Promise.all([
      base().limit(q.recent ?? 12),
      base().eq("direction", "outbound").limit(q.mine ?? 5),
    ]);
    const r = (recent.data || []) as CommItem[];
    const m = (mine.data || []) as CommItem[];
    const block = formatHistoryBlock(name, r, m);
    if (!block) return { ok: false, promptBlock: "", notice: `台帳: ${name} のやり取りなし` };
    return {
      ok: true,
      promptBlock: block,
      notice: `台帳の直近やり取り ${r.length}件＋自分の過去の文面を参照: ${name}`,
      path: `台帳: ${name}`,
      chars: block.length,
    };
  } catch (e) {
    return { ok: false, promptBlock: "", notice: `台帳読取失敗: ${e instanceof Error ? e.message : String(e)}`.slice(0, 160) };
  }
}
