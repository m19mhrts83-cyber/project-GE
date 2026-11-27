import { NextResponse } from "next/server";
import { serviceClient } from "@/lib/supabase";
import { loadDeskCards } from "@/lib/desk";
import { isLeftover } from "@/lib/deskCore";
import { loadMisses } from "@/lib/misses";
import { loadOpenTopics312 } from "@/lib/topics312";
import { loadRules } from "@/lib/rules";
import { pendingFixes } from "@/lib/zaimCore";
import { loadCloseLeak } from "@/lib/closeLeakLoad";
import { loadProposalCandidates } from "@/lib/proposalCandidates";
import { loadSlides } from "@/lib/slides";
import { loadUiux } from "@/lib/uiux";
import type { CleanupSnapshot } from "@/lib/cleanupBulk";
import type { Snapshot as WeekSnapshot } from "@/lib/weekPick";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** ハブの各項目に出す「残り対応」の件数。読めなかった項目は null（0件＝済みとは分ける） */
export type HubCounts = {
  all: number | null;
  desk: number | null;
  left: number | null;
  misses: number | null;
  drafts: number | null;
  rules: number | null;
  zaim: number | null;
  week: number | null;
  /** 312 入口＝扱いを決める＋提案を仕分ける */
  inlet: number | null;
  /** 312 の提案を仕分ける候補の id（この端末で今日仕分けた分をブラウザ側で引く） */
  proposalIds: string[] | null;
  /** 313 出口＝まとめて片付ける＋閉じ漏れ */
  outlet: number | null;
  slides: number | null;
  uiux: number | null;
  /** 判断デスクの読み込み上限に達した（60件以上） */
  deskCapped: boolean;
};

const DESK_LIMIT = 60;

export async function GET() {
  const sb = serviceClient();
  if (!sb) return NextResponse.json({ ok: false, error: "supabase_unconfigured" }, { status: 503 });
  const c: HubCounts = {
    all: null,
    desk: null,
    left: null,
    misses: null,
    drafts: null,
    rules: null,
    zaim: null,
    week: null,
    inlet: null,
    proposalIds: null,
    outlet: null,
    slides: null,
    uiux: null,
    deskCapped: false,
  };
  let topics: number | null = null;
  let cleanup: number | null = null;
  let closeLeak: number | null = null;
  const safe = (fn: () => Promise<void>) => fn().catch(() => undefined);

  await Promise.all([
    safe(async () => {
      const cards = await loadDeskCards(sb, { limit: DESK_LIMIT });
      c.desk = cards.length;
      c.deskCapped = cards.length >= DESK_LIMIT;
      const now = new Date();
      c.left = cards.filter((x) => isLeftover(x, now)).length;
    }),
    safe(async () => {
      c.misses = (await loadMisses(sb)).length;
    }),
    safe(async () => {
      const { count, error } = await sb.from("draft_reviews").select("id", { count: "exact", head: true }).eq("status", "open");
      if (!error) c.drafts = count ?? 0;
    }),
    safe(async () => {
      const r = await loadRules(sb);
      const decided = new Set(r.decided);
      c.rules = r.candidates.filter((x) => !decided.has(x.id)).length;
    }),
    safe(async () => {
      const { data, error } = await sb.from("watch_status").select("payload").eq("id", "zaim_quality").maybeSingle();
      if (!error) c.zaim = pendingFixes((data?.payload || {}) as Record<string, unknown>).length;
    }),
    safe(async () => {
      const { data, error } = await sb.from("sync_meta").select("value").eq("key", "weekly_pick_snapshot").maybeSingle();
      if (error) return;
      const w = data?.value ? (JSON.parse(String(data.value)) as WeekSnapshot) : null;
      if (!w?.week) {
        c.week = 0;
        return;
      }
      const { data: done, error: dErr } = await sb
        .from("owner_decisions")
        .select("id")
        .eq("surface", "weekly_pick")
        .eq("action", "commit")
        .eq("target_id", w.week)
        .limit(1)
        .maybeSingle();
      if (!dErr) c.week = done ? 0 : 1;
    }),
    safe(async () => {
      topics = (await loadOpenTopics312(sb, 100)).length;
    }),
    safe(async () => {
      const got = await loadProposalCandidates(sb);
      c.proposalIds = got ? got.candidates.map((x) => x.id) : [];
    }),
    safe(async () => {
      const { data, error } = await sb.from("sync_meta").select("value").eq("key", "todoist_cleanup_snapshot").maybeSingle();
      if (error) return;
      const snap = data?.value ? (JSON.parse(String(data.value)) as CleanupSnapshot) : null;
      cleanup = snap?.cards?.length ?? 0;
    }),
    safe(async () => {
      const { snapshot, cards } = await loadCloseLeak(sb);
      closeLeak = snapshot ? cards.length : 0;
    }),
    safe(async () => {
      const s = await loadSlides(sb);
      const d = s.deck;
      if (!d || d.stage === "done") {
        c.slides = 0;
        return;
      }
      c.slides = (d.stage === "plan" && !s.planned ? 1 : 0) + (d.stage === "review" ? d.proposals.filter((p) => !s.decided[p.id]).length : 0);
    }),
    safe(async () => {
      const u = await loadUiux(sb);
      const r = u.round;
      if (!r || r.stage === "done") {
        c.uiux = 0;
        return;
      }
      c.uiux = (r.stage === "plan" && !u.picked ? 1 : 0) + (r.stage === "review" ? r.proposals.filter((p) => !u.decided[p.id]).length : 0);
    }),
  ]);

  // 312 の「提案を仕分ける」はブラウザ側で今日の分を引いてから足す（ここでは扱いを決めるの件数だけ）
  c.inlet = topics;
  c.outlet = cleanup === null && closeLeak === null ? null : (cleanup ?? 0) + (closeLeak ?? 0);
  // まとめて判断（/all）に並ぶもの：メール・片付け・お題・今週の9件・Zaim・ルール候補
  const parts = [c.desk, cleanup, topics, c.week, c.zaim, c.rules];
  c.all = parts.every((x) => x === null) ? null : parts.reduce<number>((a, x) => a + (x ?? 0), 0);

  return NextResponse.json({ ok: true, ...c }, { headers: { "cache-control": "private, no-store" } });
}
