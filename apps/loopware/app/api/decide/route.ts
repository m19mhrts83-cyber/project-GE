import { NextResponse } from "next/server";
import { serviceClient } from "@/lib/supabase";

export const runtime = "nodejs";

type Body = {
  agentId?: string;
  topicText?: string;
  seedId?: string;
  proposals?: { index: number; label: string; body: string }[];
  decision?: {
    choice: string;
    chosenIndex?: number;
    finalText?: string;
    beforeText?: string;
    afterText?: string;
    reasonTags?: string[];
    freeNote?: string;
    decidedVia?: string;
    scope?: string;
  };
  todoistTaskId?: string | null;
};

export async function POST(req: Request) {
  let body: Body;
  try {
    body = (await req.json()) as Body;
  } catch {
    return NextResponse.json({ ok: false, error: "bad json" }, { status: 400 });
  }

  const sb = serviceClient();
  if (!sb) {
    return NextResponse.json({
      ok: true,
      persisted: false,
      reason: "supabase_unconfigured",
    });
  }

  const agentId = body.agentId === "313" ? "313" : "312";
  const decision = body.decision;
  if (!decision) {
    return NextResponse.json({ ok: false, error: "no decision" }, { status: 400 });
  }

  try {
    if (agentId === "313") {
      const { error } = await sb.from("owner_decisions").insert({
        surface: "todoist_313",
        action: decision.choice,
        source: decision.decidedVia || "app",
        employee: "313",
        target_type: "todoist_task",
        target_id: body.todoistTaskId || body.seedId || "-",
        subject: (body.topicText || "").slice(0, 500),
        note: decision.freeNote || null,
        payload: {
          kind: "loopware",
          proposals: body.proposals || null,
          chosen_index: decision.chosenIndex ?? null,
          reason_tags: decision.reasonTags || [],
          final_text: decision.finalText || null,
          before_text: decision.beforeText || null,
          after_text: decision.afterText || null,
          scope: decision.scope || "once",
        },
      });
      if (error) {
        return NextResponse.json({
          ok: true,
          persisted: false,
          reason: error.message,
        });
      }
      return NextResponse.json({ ok: true, persisted: true, via: "owner_decisions" });
    }

    const { data: topic, error: tErr } = await sb
      .from("task_loop_topics")
      .insert({
        agent_id: "312",
        source_kind: body.seedId?.startsWith("seed-") ? "seed" : "manual",
        topic_text: body.topicText || body.seedId || "",
        status: "decided",
      })
      .select("id")
      .single();
    if (tErr || !topic) {
      return NextResponse.json({
        ok: true,
        persisted: false,
        reason: tErr?.message || "topic insert failed",
      });
    }

    const props = body.proposals || [];
    if (props.length) {
      await sb.from("task_loop_proposals").insert(
        props.map((p) => ({
          topic_id: topic.id,
          proposal_index: p.index,
          label: p.label,
          body: p.body,
          prompt_version: "seed-v1",
        })),
      );
    }

    await sb.from("task_loop_decisions").upsert({
      topic_id: topic.id,
      chosen_index: decision.chosenIndex ?? null,
      choice: decision.choice,
      final_text: decision.finalText || null,
      before_text: decision.beforeText || null,
      after_text: decision.afterText || null,
      reason_tags: decision.reasonTags || [],
      free_note: decision.freeNote || null,
      decided_via: decision.decidedVia || "app",
      updated_at: new Date().toISOString(),
    });

    return NextResponse.json({
      ok: true,
      persisted: true,
      via: "task_loop",
      topicId: topic.id,
    });
  } catch (e) {
    return NextResponse.json({
      ok: true,
      persisted: false,
      reason: e instanceof Error ? e.message : String(e),
    });
  }
}
