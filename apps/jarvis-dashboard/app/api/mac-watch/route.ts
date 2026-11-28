import { NextResponse, type NextRequest } from "next/server";
import { createServiceClient } from "@/lib/supabase/admin";
import { bearerMatches } from "@/lib/obsidianReviewAgent";
import { decide, isStale, type WatchState } from "@/lib/macWatch";

/**
 * Mac 見張り（2026-11-13 従量課金ゼロ化で Mac の定額AIに寄せたため）。
 * Supabase pg_cron が 5 分ごとに呼ぶ。状態が変わったときだけ Slack #ops に出す。
 *  - mac: Mac の常駐ポーラー（60 秒ごと）の最終応答が 15 分以上前 → 🔴
 *  - flat_ai_worker: 定額AIの係の心拍が 15 分以上前（Mac は生きている）→ 🔴
 * 瞬断の連投を避けるため、2 回連続（5 分×2）で止まりと判定された時だけ 🔴（2026-11-28）。
 * 復旧したら 🟢 を 1 回。連続回数は mac_watch_status.offline_streak に持つ。
 */
export const runtime = "nodejs";
export const maxDuration = 15;

type Check = { id: "mac" | "flat_ai_worker"; last: string | null; title: string; down: string; up: string };

function jst(value: string | null): string {
  if (!value) return "未受信";
  return new Intl.DateTimeFormat("ja-JP", {
    timeZone: "Asia/Tokyo", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(new Date(value));
}

export async function POST(request: NextRequest) {
  if (!bearerMatches(request, "MAC_WATCH_KEY", ["OBSIDIAN_REVIEW_MONITOR_KEY", "PROPERTY_GATE_ACTION_TOKEN"])) {
    return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  }
  const sb = createServiceClient();
  if (!sb) return NextResponse.json({ ok: false, error: "not_configured" }, { status: 503 });

  const [{ data: poller }, { data: meta }, { data: states, error: statesError }] = await Promise.all([
    sb.from("obsidian_review_agent_status").select("last_poll_at").eq("agent_id", "mac").maybeSingle(),
    sb.from("sync_meta").select("key,value,updated_at").eq("key", "flat_ai_worker_at").maybeSingle(),
    sb.from("mac_watch_status").select("check_id,notified_state,offline_streak"),
  ]);
  // 状態が読めないのに「状態なし」として通知しない（migration 未適用など）
  if (statesError) return NextResponse.json({ ok: false, error: "state_read_failed" }, { status: 503 });
  const prev = new Map<string, string>((states || []).map((r) => [String(r.check_id), String(r.notified_state)]));
  const prevStreak = new Map<string, number>((states || []).map((r) => [String(r.check_id), Number(r.offline_streak) || 0]));
  const now = Date.now();
  const stale = (iso: string | null) => isStale(iso, now);

  const macLast = (poller?.last_poll_at as string | null) ?? null;
  const workerLast = (meta?.updated_at as string | null) ?? null;
  const macDown = stale(macLast);

  const checks: Check[] = [
    {
      id: "mac",
      last: macLast,
      title: "Mac（自動化の土台）",
      down: "Macから15分以上応答がありません。定額AIの係・定期実行が止まっています。電源／ネット／再起動後のログインを確認してください。止まっている間の依頼は、再開後に順に処理します。",
      up: "Macの応答が戻りました。止まっていた間の依頼から順に処理します。",
    },
    {
      id: "flat_ai_worker",
      last: workerLast,
      title: "定額AIの係（返信案・和訳など）",
      down: "Macは動いていますが、定額AIの係が15分以上止まっています。launchd com.matsunoma.jarvis.flat-ai-worker を確認してください。",
      up: "定額AIの係が動き始めました。",
    },
  ];

  const webhook = (process.env.SLACK_WEBHOOK_AI_TEAM_OPS || "").trim();
  const results: Record<string, string> = {};
  for (const c of checks) {
    const before = (prev.get(c.id) || "unknown") as WatchState;
    const streak = prevStreak.get(c.id) || 0;
    // Mac ごと止まっているときは係の通知を重ねない（状態も連続回数もそのまま）
    if (c.id === "flat_ai_worker" && macDown) {
      results[c.id] = before;
      continue;
    }
    const d = decide(before, streak, stale(c.last));
    results[c.id] = d.state;
    if (d.state === before && d.streak === streak) continue;
    const changedAt = new Date().toISOString();
    // 初回の online は無言。復旧通知は止まりを通知済み（offline）のときだけ
    if (d.notify) {
      if (!webhook) return NextResponse.json({ ok: false, error: "ops_webhook_missing" }, { status: 503 });
      const text = d.notify === "down"
        ? `【停止】${c.title}\n判定: 🔴 要対応\n${c.down}\n最後の応答: ${jst(c.last)}（JST）`
        : `【復旧】${c.title}\n判定: 🟢 回っています\n${c.up}\n最終応答: ${jst(c.last)}（JST）`;
      const res = await fetch(webhook, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }), cache: "no-store",
      }).catch(() => null);
      if (!res || !res.ok) return NextResponse.json({ ok: false, error: "notification_failed" }, { status: 503 });
    }
    await sb.from("mac_watch_status")
      .update({
        notified_state: d.state,
        offline_streak: d.streak,
        ...(d.state !== before ? { state_changed_at: changedAt } : {}),
        updated_at: changedAt,
      })
      .eq("check_id", c.id);
  }
  return NextResponse.json({ ok: true, states: results, mac_last: macLast, worker_last: workerLast });
}
