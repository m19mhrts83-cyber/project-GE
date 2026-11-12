import { NextResponse, type NextRequest } from "next/server";
import { createServiceClient } from "@/lib/supabase/admin";
import { bearerMatches } from "@/lib/obsidianReviewAgent";

export const runtime = "nodejs";
export const maxDuration = 15;

const STALE_MS = 5 * 60 * 1000;
const STARTUP_GRACE_MS = 10 * 60 * 1000;

function jst(value: string | null): string {
  if (!value) return "未受信";
  return new Intl.DateTimeFormat("ja-JP", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

/** Called by the private time-driven monitor. Posts only on state transitions. */
export async function POST(request: NextRequest) {
  if (!bearerMatches(request, "OBSIDIAN_REVIEW_MONITOR_KEY", [
    "OBSIDIAN_REVIEW_SUBMIT_KEY", "OBSIDIAN_REVIEW_POLL_KEY", "OBSIDIAN_REVIEW_READ_KEY", "OBSIDIAN_VAULT_POLL_KEY",
  ])) {
    return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  }
  const supabase = createServiceClient();
  if (!supabase) return NextResponse.json({ ok: false, error: "monitor_not_configured" }, { status: 503 });

  const { data: state, error } = await supabase
    .from("obsidian_review_agent_status")
    .select("agent_id,first_observed_at,monitor_started_at,last_poll_at,notified_state,created_at")
    .eq("agent_id", "mac")
    .maybeSingle();
  if (error || !state) {
    console.error("obsidian_review_monitor_state_failed", error?.code || "missing_state");
    return NextResponse.json({ ok: false, error: "monitor_state_unavailable" }, { status: 503 });
  }

  const now = Date.now();
  const lastPoll = state.last_poll_at ? Date.parse(state.last_poll_at) : null;
  const previous = state.notified_state as "unknown" | "online" | "offline";
  if (lastPoll === null && previous === "unknown" && !state.monitor_started_at) {
    const firstCheck = new Date().toISOString();
    const { error: startError } = await supabase
      .from("obsidian_review_agent_status")
      .update({ monitor_started_at: firstCheck, updated_at: firstCheck })
      .eq("agent_id", "mac")
      .eq("notified_state", "unknown")
      .is("monitor_started_at", null)
      .is("last_poll_at", null);
    if (startError) return NextResponse.json({ ok: false, error: "monitor_state_unavailable" }, { status: 503 });
    return NextResponse.json({ ok: true, state: "starting", changed: false, startup_grace_minutes: 10 });
  }
  const baseline = lastPoll ?? Date.parse(state.monitor_started_at || state.first_observed_at || state.created_at);
  const threshold = lastPoll === null ? STARTUP_GRACE_MS : STALE_MS;
  const observedState = now - baseline > threshold ? "offline" : "online";

  if (observedState === previous) {
    return NextResponse.json({ ok: true, state: observedState, changed: false, last_poll_at: state.last_poll_at });
  }
  if (previous === "unknown" && observedState === "online") {
    const { error: initError } = await supabase
      .from("obsidian_review_agent_status")
      .update({ notified_state: "online", state_changed_at: new Date().toISOString(), updated_at: new Date().toISOString() })
      .eq("agent_id", "mac")
      .eq("notified_state", "unknown");
    if (initError) return NextResponse.json({ ok: false, error: "state_update_failed" }, { status: 503 });
    return NextResponse.json({ ok: true, state: observedState, changed: false, last_poll_at: state.last_poll_at });
  }

  const webhook = (process.env.SLACK_WEBHOOK_AI_TEAM_OPS || "").trim();
  if (!webhook) {
    console.error("obsidian_review_monitor_slack_not_configured");
    return NextResponse.json({ ok: false, error: "ops_notification_not_configured" }, { status: 503 });
  }
  const message = observedState === "offline"
    ? `【障害】814 Obsidian日次連携\nMacのVaultポーラーから5分以上応答がありません。最後の応答: ${jst(state.last_poll_at)}（JST）。Mac／ネットワーク／LaunchAgentを確認してください。`
    : `【復旧】814 Obsidian日次連携\nMacのVaultポーラーが応答を再開しました。最終応答: ${jst(state.last_poll_at)}（JST）。`;
  let slackResponse: Response;
  try {
    slackResponse = await fetch(webhook, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: message }),
      cache: "no-store",
    });
  } catch {
    console.error("obsidian_review_monitor_slack_post_failed", "network_error");
    return NextResponse.json({ ok: false, error: "notification_failed" }, { status: 503 });
  }
  if (!slackResponse.ok) {
    console.error("obsidian_review_monitor_slack_post_failed", `http_${slackResponse.status}`);
    return NextResponse.json({ ok: false, error: "notification_failed" }, { status: 503 });
  }

  const changedAt = new Date().toISOString();
  const { error: updateError } = await supabase
    .from("obsidian_review_agent_status")
    .update({ notified_state: observedState, state_changed_at: changedAt, updated_at: changedAt })
    .eq("agent_id", "mac")
    .eq("notified_state", previous);
  if (updateError) {
    console.error("obsidian_review_monitor_state_update_failed", updateError.code || "db_error");
    return NextResponse.json({ ok: false, error: "state_update_failed" }, { status: 503 });
  }
  return NextResponse.json({ ok: true, state: observedState, changed: true, last_poll_at: state.last_poll_at });
}
