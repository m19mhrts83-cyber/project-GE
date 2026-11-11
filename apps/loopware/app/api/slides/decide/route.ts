import { NextResponse } from "next/server";
import { serviceClient } from "@/lib/supabase";
import { writeDecision } from "@/lib/ownerDecisionLog";
import { loadDeck } from "@/lib/slides";
import { planComplete, ruleKey } from "@/lib/slidesCore";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const RULE_ACTION = { accept: "rule_accept", once: "rule_once", reject: "rule_reject", revert: "rule_revert" } as const;

type Body = {
  kind?: "plan" | "rule";
  deckId?: string;
  idemKey?: string;
  note?: string;
  // plan
  plan?: string | null;
  axes?: Record<string, number>;
  notChosen?: { plan: string; tags?: string[] }[];
  // rule
  proposalId?: string;
  verdict?: keyof typeof RULE_ACTION;
  tags?: string[];
  // revert（過去のデッキの基準も取り消せるよう、本文は送ってもらう）
  ruleKey?: string;
  text?: string;
};

/**
 * 資料の判断を記録する。中身（案・反映案の本文）はサーバ側のデッキから引く（画面の値は信じない）。
 * - kind=plan：作る前の選択（案1つ＋観点＋選ばなかった案の理由タグ）→ slide_plan / adopt
 * - kind=rule：次回反映案の 採用／今回だけ／違う、採用済みの 取り消す → slide_rule
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
      surface: "slide_rule",
      action: "rule_revert",
      source: "loopware",
      targetType: "slide_proposal",
      targetId: rk,
      idemKey: key,
      note: b.note,
      payload: { deck_id: rk.split(":")[0], proposal_id: rk.split(":")[1], text: String(b.text || "").slice(0, 300) },
    });
    return NextResponse.json(r, { status: r.ok ? 200 : 400 });
  }

  const deck = await loadDeck(sb);
  if (!deck || deck.id !== b.deckId) return NextResponse.json({ ok: false, error: "deck_changed" }, { status: 409 });

  if (b.kind === "plan") {
    const axesIdx = b.axes || {};
    if (!planComplete(deck, { plan: b.plan ?? null, axes: axesIdx })) return NextResponse.json({ ok: false, error: "incomplete" }, { status: 400 });
    const chosen = deck.plans.find((p) => p.id === b.plan) || null;
    const axes: Record<string, string> = {};
    for (const a of deck.axes) axes[a.key] = a.options[axesIdx[a.key]];
    const notChosen = deck.plans
      .filter((p) => p.id !== b.plan)
      .map((p) => {
        const hit = (b.notChosen || []).find((n) => n.plan === p.id);
        return { plan: p.id, label: p.label, tags: (hit?.tags || []).map(String).slice(0, 5) };
      });
    const r = await writeDecision(sb, {
      surface: "slide_plan",
      action: "adopt",
      source: "loopware",
      targetType: "slide_deck",
      targetId: deck.id,
      subject: deck.title,
      aiProposal: chosen ? `${chosen.label}：${chosen.summary}` : null,
      note: b.note,
      idemKey: key,
      reasonTags: notChosen.flatMap((n) => n.tags),
      appliedRules: chosen?.applied || [],
      payload: {
        deck_id: deck.id,
        plan: chosen?.id || null,
        plan_label: chosen?.label || null,
        plan_order: deck.plans.map((p) => p.id),
        axes,
        not_chosen: notChosen,
      },
    });
    return NextResponse.json(r, { status: r.ok ? 200 : 400 });
  }

  if (b.kind === "rule" && b.verdict && b.verdict in RULE_ACTION) {
    const p = deck.proposals.find((x) => x.id === b.proposalId);
    if (!p) return NextResponse.json({ ok: false, error: "proposal" }, { status: 400 });
    const r = await writeDecision(sb, {
      surface: "slide_rule",
      action: RULE_ACTION[b.verdict],
      source: "loopware",
      targetType: "slide_proposal",
      targetId: ruleKey(deck.id, p.id),
      subject: deck.title,
      idemKey: key,
      note: b.note,
      reasonTags: (b.tags || []).map(String),
      scope: b.verdict === "once" ? "once" : b.verdict === "accept" ? "always" : null,
      payload: { deck_id: deck.id, proposal_id: p.id, text: p.text, why: p.why, concept: p.concept || null, evidence: p.evidence || [] },
    });
    return NextResponse.json(r, { status: r.ok ? 200 : 400 });
  }

  return NextResponse.json({ ok: false, error: "kind / verdict" }, { status: 400 });
}
