import { NextResponse } from "next/server";
import { serviceClient } from "@/lib/supabase";
import { writeDecision } from "@/lib/ownerDecisionLog";
import { loadRound } from "@/lib/uiux";
import { PLAN_VERDICTS, pickAction, pickComplete, ruleKey, type PlanVerdict } from "@/lib/uiuxCore";
import { UIUX_PLAN_REASON_TAGS, UIUX_RULE_REASON_TAGS } from "@/lib/decisionContract";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const EMPLOYEE = "814"; // 好み帳の預かり（800_俯瞰UI・投影更新室）
const RULE_ACTION = { accept: "rule_accept", once: "rule_once", reject: "rule_reject", revert: "rule_revert" } as const;

type Body = {
  kind?: "plan" | "rule";
  roundId?: string;
  idemKey?: string;
  note?: string;
  // plan
  chosen?: string | null;
  verdicts?: Record<string, string>;
  tags?: Record<string, string[]> | string[];
  // rule
  proposalId?: string;
  verdict?: keyof typeof RULE_ACTION;
  ruleKey?: string;
  text?: string;
};

function onlyKnown(xs: unknown, known: Record<string, string>): string[] {
  return (Array.isArray(xs) ? xs : []).map(String).filter((t) => t in known).slice(0, 6);
}

/**
 * UI/UX の判断を記録する。案・ルール案の中身はサーバ側のラウンドから引く（画面の値は信じない）。
 * - kind=plan：案ごとの 良い／違う／迷う＋理由タグ、選んだ案（無ければ「どれも違う」）→ uiux_plan
 * - kind=rule：好みルール案の 採用／今回だけ／違う、採用済みの 取り消す → uiux_rule
 */
export async function POST(req: Request) {
  let b: Body;
  try {
    b = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "bad json" }, { status: 400 });
  }
  const key = String(b.idemKey || "");
  if (key.length < 8) return NextResponse.json({ ok: false, error: "idemKey" }, { status: 400 });
  const sb = serviceClient();
  if (!sb) return NextResponse.json({ ok: false, error: "supabase_unconfigured" }, { status: 503 });

  if (b.kind === "rule" && b.verdict === "revert") {
    const rk = String(b.ruleKey || "");
    if (!/^[A-Za-z0-9_.-]{1,80}:[A-Za-z0-9_-]{1,40}$/.test(rk)) return NextResponse.json({ ok: false, error: "ruleKey" }, { status: 400 });
    const r = await writeDecision(sb, {
      surface: "uiux_rule",
      action: "rule_revert",
      source: "loopware",
      employee: EMPLOYEE,
      targetType: "uiux_proposal",
      targetId: rk,
      idemKey: key,
      note: b.note,
      payload: { round_id: rk.split(":")[0], proposal_id: rk.split(":")[1], text: String(b.text || "").slice(0, 300) },
    });
    return NextResponse.json(r, { status: r.ok ? 200 : 400 });
  }

  const round = await loadRound(sb);
  if (!round || round.id !== b.roundId) return NextResponse.json({ ok: false, error: "round_changed" }, { status: 409 });

  if (b.kind === "plan") {
    const verdicts: Record<string, PlanVerdict> = {};
    const tags: Record<string, string[]> = {};
    const inTags = (b.tags && !Array.isArray(b.tags) ? b.tags : {}) as Record<string, string[]>;
    for (const p of round.plans) {
      const v = String(b.verdicts?.[p.id] || "");
      if ((PLAN_VERDICTS as readonly string[]).includes(v)) verdicts[p.id] = v as PlanVerdict;
      const t = onlyKnown(inTags[p.id], UIUX_PLAN_REASON_TAGS);
      if (t.length) tags[p.id] = t;
    }
    const chosen = b.chosen && round.plans.some((p) => p.id === b.chosen) ? String(b.chosen) : null;
    if (chosen) verdicts[chosen] = "good";
    const pick = { chosen, verdicts, tags };
    if (!pickComplete(round, pick)) return NextResponse.json({ ok: false, error: "incomplete" }, { status: 400 });
    const action = pickAction(round, pick);
    const c = round.plans.find((p) => p.id === chosen) || null;
    const r = await writeDecision(sb, {
      surface: "uiux_plan",
      action,
      source: "loopware",
      employee: EMPLOYEE,
      targetType: "uiux_round",
      targetId: round.id,
      subject: round.title,
      aiProposal: c ? `${c.label}：${c.summary}` : null,
      note: b.note,
      idemKey: key,
      quality: chosen ? null : action === "reject" ? "none_fit" : null,
      reasonTags: [...new Set(Object.values(tags).flat())],
      appliedRules: c?.applied || [],
      payload: {
        round_id: round.id,
        app: round.app,
        screen: round.screen || null,
        pr: round.pr || null,
        chosen,
        plan_order: round.plans.map((p) => p.id),
        verdicts,
        tags,
      },
    });
    return NextResponse.json(r, { status: r.ok ? 200 : 400 });
  }

  if (b.kind === "rule" && b.verdict && b.verdict in RULE_ACTION) {
    const p = round.proposals.find((x) => x.id === b.proposalId);
    if (!p) return NextResponse.json({ ok: false, error: "proposal" }, { status: 400 });
    const r = await writeDecision(sb, {
      surface: "uiux_rule",
      action: RULE_ACTION[b.verdict],
      source: "loopware",
      employee: EMPLOYEE,
      targetType: "uiux_proposal",
      targetId: ruleKey(round.id, p.id),
      subject: round.title,
      idemKey: key,
      note: b.note,
      reasonTags: onlyKnown(b.tags, UIUX_RULE_REASON_TAGS),
      scope: b.verdict === "once" ? "once" : b.verdict === "accept" ? "always" : null,
      payload: { round_id: round.id, proposal_id: p.id, text: p.text, why: p.why, concept: p.concept || null, app: p.app || "*", evidence: p.evidence || [] },
    });
    return NextResponse.json(r, { status: r.ok ? 200 : 400 });
  }

  return NextResponse.json({ ok: false, error: "kind / verdict" }, { status: 400 });
}
