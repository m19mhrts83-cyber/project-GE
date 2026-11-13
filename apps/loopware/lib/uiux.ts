/**
 * UI/UX の好みループの読み込み（サーバ専用）。
 * いまのラウンド（画面の案・好みルール案）は sync_meta.loopware_uiux に、エージェントが scripts/jarvis_uiux_loop.py で置く。
 * 判断は owner_decisions（surface = uiux_plan / uiux_fix / uiux_rule）。
 * 画像は Supabase Storage の非公開バケット uiux-shots（"storage:<パス>"）を1時間の署名付き URL にして返す。
 */
import type { SupabaseClient } from "@supabase/supabase-js";
import { adoptedUiuxRules, decidedProposals, parseRound, type UiuxRound, type UiuxRule } from "@/lib/uiuxCore";

export const UIUX_META_KEY = "loopware_uiux";
export const UIUX_BUCKET = "uiux-shots";

export type UiuxPicked = {
  chosen: string | null;
  action: string;
  verdicts: Record<string, string>;
  at: string;
} | null;

export type UiuxState = {
  round: UiuxRound | null;
  rules: UiuxRule[];
  decided: Record<string, string>;
  picked: UiuxPicked;
  /** 直近の画面づくりの手応え（エージェントが記録した uiux_fix の集計） */
  recent: { works: number; firstOk: number; avgTrips: number | null };
};

export async function loadRound(sb: SupabaseClient): Promise<UiuxRound | null> {
  const { data } = await sb.from("sync_meta").select("value").eq("key", UIUX_META_KEY).maybeSingle();
  return data ? parseRound(data.value) : null;
}

async function signImages(sb: SupabaseClient, round: UiuxRound): Promise<UiuxRound> {
  const plans = await Promise.all(
    round.plans.map(async (p) => {
      if (!p.image?.startsWith("storage:")) return p;
      const path = p.image.slice("storage:".length);
      try {
        const { data } = await sb.storage.from(UIUX_BUCKET).createSignedUrl(path, 3600);
        return { ...p, image: data?.signedUrl || undefined };
      } catch {
        return { ...p, image: undefined };
      }
    }),
  );
  return { ...round, plans };
}

type FixRow = { action: string; payload: Record<string, unknown> | null };

/** uiux_fix の行を「1つの画面づくり（work）」ごとに束ね、1案目OK率と平均往復回数を出す */
export function fixSummary(rows: FixRow[]): UiuxState["recent"] {
  const works = new Map<string, { first: string | null; trips: number }>();
  for (const r of rows) {
    const pl = r.payload || {};
    const work = String(pl.work_id || "");
    if (!work) continue;
    const trip = Number(pl.round_trip) || 1;
    const w = works.get(work) || { first: null, trips: 0 };
    if (trip === 1 && w.first === null) w.first = r.action;
    w.trips = Math.max(w.trips, trip);
    works.set(work, w);
  }
  const list = [...works.values()];
  const firstOk = list.filter((w) => w.first === "good").length;
  return {
    works: list.length,
    firstOk,
    avgTrips: list.length ? Math.round((list.reduce((s, w) => s + w.trips, 0) / list.length) * 10) / 10 : null,
  };
}

export async function loadUiux(sb: SupabaseClient): Promise<UiuxState> {
  const raw = await loadRound(sb);
  const round = raw ? await signImages(sb, raw) : null;
  const { data: ruleRows } = await sb
    .from("owner_decisions")
    .select("action,target_id,payload,decided_at")
    .eq("surface", "uiux_rule")
    .order("decided_at", { ascending: false })
    .limit(500);
  const rows = (ruleRows || []).map((r) => ({
    action: String(r.action),
    target_id: String(r.target_id),
    payload: (r.payload || {}) as Record<string, unknown>,
    decided_at: String(r.decided_at || ""),
  }));
  let picked: UiuxPicked = null;
  if (round) {
    const { data: p } = await sb
      .from("owner_decisions")
      .select("action,payload,decided_at")
      .eq("surface", "uiux_plan")
      .eq("target_id", round.id)
      .order("decided_at", { ascending: false })
      .limit(1)
      .maybeSingle();
    if (p) {
      const pl = (p.payload || {}) as Record<string, unknown>;
      picked = {
        chosen: pl.chosen ? String(pl.chosen) : null,
        action: String(p.action),
        verdicts: (pl.verdicts || {}) as Record<string, string>,
        at: String(p.decided_at || ""),
      };
    }
  }
  const since = new Date(Date.now() - 90 * 864e5).toISOString();
  const { data: fixRows } = await sb
    .from("owner_decisions")
    .select("action,payload")
    .eq("surface", "uiux_fix")
    .gte("decided_at", since)
    .limit(2000);
  return {
    round,
    rules: adoptedUiuxRules(rows),
    decided: round ? decidedProposals(rows, round.id) : {},
    picked,
    recent: fixSummary((fixRows || []) as FixRow[]),
  };
}
