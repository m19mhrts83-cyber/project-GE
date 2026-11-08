import { NextResponse } from "next/server";
import { serviceClient } from "@/lib/supabase";
import { writeDecision } from "@/lib/ownerDecisionLog";
import type { RuleCandidate } from "@/lib/rules";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ACTION = { accept: "rule_accept", once: "rule_once", reject: "rule_reject", revert: "rule_revert" } as const;

/**
 * ルール候補への 採用／今回だけ／違う、採用済みルールの 取り消す。
 * 採用の1回が承認（PR を人が見直さない）。反映は jarvis_loopware_apply_rules.py が1ルール=1コミットで行う。
 */
export async function POST(req: Request) {
  let b: { verdict?: keyof typeof ACTION; idemKey?: string; candidate?: RuleCandidate; ruleId?: string; employee?: string; text?: string };
  try {
    b = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "bad json" }, { status: 400 });
  }
  const verdict = b.verdict;
  const key = String(b.idemKey || "");
  if (!verdict || !(verdict in ACTION) || key.length < 8) {
    return NextResponse.json({ ok: false, error: "verdict / idemKey" }, { status: 400 });
  }
  const sb = serviceClient();
  if (!sb) return NextResponse.json({ ok: false, error: "supabase_unconfigured" }, { status: 503 });

  if (verdict === "revert") {
    if (!b.ruleId || !/^R\w+-\d+$/.test(b.ruleId)) return NextResponse.json({ ok: false, error: "ruleId" }, { status: 400 });
    const r = await writeDecision(sb, {
      surface: "rule_review",
      action: "rule_revert",
      source: "loopware",
      targetType: "rule",
      targetId: b.ruleId,
      employee: b.employee,
      idemKey: key,
      payload: { rule_id: b.ruleId, employee: b.employee, text: b.text || null },
    });
    return NextResponse.json(r, { status: r.ok ? 200 : 400 });
  }

  const c = b.candidate;
  if (!c || !/^C[0-9a-f]{8}$/.test(String(c.id))) return NextResponse.json({ ok: false, error: "candidate" }, { status: 400 });
  const r = await writeDecision(sb, {
    surface: "rule_review",
    action: ACTION[verdict],
    source: "loopware",
    targetType: "rule_candidate",
    targetId: c.id,
    employee: c.employee,
    idemKey: key,
    scope: verdict === "once" ? "once" : "always",
    payload: {
      candidate_id: c.id,
      kind: c.kind,
      employee: c.employee,
      rule_line: c.rule_line,
      text: c.text,
      why: c.why,
      evidence: (c.evidence || []).slice(0, 10),
      ladder: c.status,
    },
  });
  return NextResponse.json(r, { status: r.ok ? 200 : 400 });
}
