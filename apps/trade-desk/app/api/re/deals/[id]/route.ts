import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";

type Action =
  | "confirm"
  | "pass"
  | "pursue_add"
  | "pursue_remove"
  | "set_viewing"
  | "set_offer";

const FUNNEL_KEEP = new Set(["viewing", "offer", "loan", "purchased"]);

function nextStatus(action: Action, current: string): string {
  if (action === "pass") return "passed";
  if (action === "pursue_remove") return current;
  if (action === "pursue_add") return current; // フォロー印のみ。status は変えない
  if (action === "confirm") {
    // 仕分けのみ。内見に上げない
    if (current === "passed") return "info";
    return current || "info";
  }
  if (action === "set_viewing") {
    if (FUNNEL_KEEP.has(current) && current !== "viewing") return current;
    return "viewing";
  }
  if (action === "set_offer") {
    if (current === "loan" || current === "purchased") return current;
    return "offer";
  }
  return current;
}

function eventMeta(
  action: Action
): { event_type: string; summary: string } {
  switch (action) {
    case "confirm":
      return {
        event_type: "review_confirm",
        summary: "仕分け済・詳細問合せへ",
      };
    case "pass":
      return { event_type: "review_pass", summary: "対象外（見送り）" };
    case "pursue_add":
      return {
        event_type: "status_change",
        summary: "進行中（詳細〜内見）に追加",
      };
    case "pursue_remove":
      return {
        event_type: "status_change",
        summary: "進行中から外す",
      };
    case "set_viewing":
      return { event_type: "status_change", summary: "内見にする" };
    case "set_offer":
      return {
        event_type: "status_change",
        summary: "買付へ（買い進め・買付証明）",
      };
  }
}

export async function POST(
  req: Request,
  ctx: { params: Promise<{ id: string }> }
) {
  const { id } = await ctx.params;
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const body = await req.json().catch(() => ({}));
  const action = String(body.action || "") as Action;
  const allowed: Action[] = [
    "confirm",
    "pass",
    "pursue_add",
    "pursue_remove",
    "set_viewing",
    "set_offer",
  ];
  if (!allowed.includes(action)) {
    return NextResponse.json(
      {
        error:
          "action must be confirm | pass | pursue_add | pursue_remove | set_viewing | set_offer",
      },
      { status: 400 }
    );
  }

  const { data: row, error: getErr } = await supabase
    .from("kurashift_re_deals")
    .select("id, title, status, source, summary_json")
    .eq("id", id)
    .maybeSingle();
  if (getErr || !row) {
    return NextResponse.json(
      { error: getErr?.message || "not found" },
      { status: 404 }
    );
  }

  const sj =
    row.summary_json && typeof row.summary_json === "object"
      ? (row.summary_json as Record<string, unknown>)
      : {};
  const gmailId = typeof sj.gmail_id === "string" ? sj.gmail_id : null;
  const alreadyRead =
    typeof sj.gmail_read_at === "string" && sj.gmail_read_at.length > 0;

  const status = nextStatus(action, String(row.status || "info"));
  const now = new Date().toISOString();

  if (action === "confirm") {
    // 仕分け印のみ。進行中ブロックには入れない
    sj.user_confirmed = true;
    sj.user_confirmed_at = now;
    delete sj.pursue_exclude;
    delete sj.pursue_exclude_at;
  }
  if (action === "pursue_add") {
    sj.pursue = true;
    sj.pursue_at = now;
    delete sj.pursue_exclude;
    delete sj.pursue_exclude_at;
  }
  if (action === "pass") {
    delete sj.pursue;
    delete sj.pursue_at;
    sj.user_confirmed = false;
    sj.pursue_exclude = true;
    sj.pursue_exclude_at = now;
  }
  if (action === "pursue_remove") {
    delete sj.pursue;
    delete sj.pursue_at;
    sj.pursue_exclude = true;
    sj.pursue_exclude_at = now;
  }
  if (action === "set_viewing" || action === "set_offer") {
    delete sj.pursue_exclude;
    delete sj.pursue_exclude_at;
  }

  const { data: updated, error: upErr } = await supabase
    .from("kurashift_re_deals")
    .update({ status, summary_json: sj, updated_at: now })
    .eq("id", id)
    .select("id, title, status, source")
    .single();
  if (upErr || !updated) {
    return NextResponse.json(
      { error: upErr?.message || "update failed" },
      { status: 500 }
    );
  }

  const prevStatus = String(row.status || "info");
  const { event_type, summary } = eventMeta(action);
  await supabase.from("kurashift_re_deal_events").insert({
    deal_id: id,
    event_type,
    from_status: prevStatus,
    to_status: status,
    actor: "user",
    summary,
    payload: { action },
  });

  // 取込時に既読済みが本線。確認／対象外は未既読の残りだけキュー。
  let mark_read_queued = false;
  let mark_read_skipped: string | null = null;
  let job_id: string | null = null;

  const wantMarkRead = action === "confirm" || action === "pass";
  if (wantMarkRead) {
    if (!gmailId) {
      mark_read_skipped = "no_gmail_id";
    } else if (alreadyRead) {
      mark_read_skipped = "already_read";
    } else {
      const jobTitle =
        action === "confirm"
          ? `Gmail既読（確認）: ${String(row.title || "").slice(0, 60)}`
          : `Gmail既読（対象外）: ${String(row.title || "").slice(0, 60)}`;
      const { data: job, error: jobErr } = await supabase
        .from("kurashift_jobs")
        .insert({
          job_type: "re_deal_mark_gmail_read",
          title: jobTitle,
          status: "queued",
          payload: {
            deal_id: id,
            action,
            gmail_id: gmailId,
            source: row.source || sj.account || null,
          },
          created_by: user.email ?? user.id,
        })
        .select("id")
        .single();
      if (jobErr) {
        return NextResponse.json(
          {
            ok: true,
            deal: updated,
            mark_read_queued: false,
            mark_read_skipped: null,
            warning: `status更新済・既読ジョブ失敗: ${jobErr.message}`,
          },
          { status: 200 }
        );
      }
      mark_read_queued = true;
      job_id = job?.id ?? null;
    }
  } else {
    mark_read_skipped = "funnel_ui_only";
  }

  return NextResponse.json({
    ok: true,
    deal: updated,
    mark_read_queued,
    mark_read_skipped,
    job_id,
  });
}
