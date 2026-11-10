/**
 * Run: npx tsx lib/kurashiftDecisionLog.selftest.ts
 */
import { appendMoneyDecision, parseDecisionNote } from "./kurashiftDecision";
import { dealRows, moneyRows, sortNewest, summarize } from "./kurashiftDecisionLog";

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg);
}

// 理由は任意。知らないタグは捨て、scope は once／always だけ
const n = parseDecisionNote({ reason_tags: ["plan_fit", "plan_fit", "evil"], note: "  予定どおり ", scope: "always" });
assert(n && n.reason_tags.length === 1 && n.reason_tags[0] === "plan_fit", "tags cleaned");
assert(n!.note === "予定どおり" && n!.scope === "always", "note/scope");
assert(parseDecisionNote(null) === null, "no decision → null");
assert(parseDecisionNote({ scope: "partner" })!.scope === "once", "unknown scope → once");

// 痕跡は追記のみ・最大50件
let ap: Record<string, unknown> = { due_date: "2026-11-26" };
for (let i = 0; i < 55; i++) {
  ap = appendMoneyDecision(ap, {
    at: `2026-11-10T00:${String(i).padStart(2, "0")}:00Z`,
    from: "draft",
    to: i % 2 ? "approved" : "executing",
    action: "accept",
    by: "me",
    reason_tags: i < 3 ? ["buffer"] : [],
    note: null,
    scope: i === 1 ? "always" : "once",
    amount_jpy: 100000,
  });
}
assert((ap.decision_log as unknown[]).length === 50, "log capped at 50");
assert(ap.due_date === "2026-11-26", "other payload kept");
assert((ap.last_decision as { at: string }).at.endsWith("54:00Z"), "last_decision is newest");

// 実行中へ（executing）は判断に数えない
const m = moneyRows([
  {
    id: "op1",
    title: "寄せ",
    amount_jpy: 100000,
    assist_payload: {
      decision_log: [
        { at: "2026-11-01T00:00:00Z", to: "approved", reason_tags: ["buffer"], scope: "always" },
        { at: "2026-11-02T00:00:00Z", to: "executing" },
        { at: "2026-11-03T00:00:00Z", to: "cancelled", reason_tags: ["buffer"], note: "時期をずらす" },
      ],
    },
  },
]);
assert(m.length === 2, `money rows: ${m.length}`);
assert(m[0].label === "承認" && m[0].always, "approve row");

const d = dealRows(
  [
    { id: "e1", deal_id: "x", event_type: "review_pass", actor: "user", occurred_at: "2026-11-04T00:00:00Z", payload: { action: "pass", reason_tags: ["yield"] } },
    { id: "e2", deal_id: "y", event_type: "review_pass", actor: "user", occurred_at: "2026-11-05T00:00:00Z", payload: { action: "pass", reason_tags: ["yield"], note: "7%未満" } },
    { id: "e3", deal_id: "y", event_type: "note", actor: "grok", occurred_at: "2026-11-05T00:00:00Z", payload: {} },
    { id: "e4", deal_id: "z", event_type: "status_change", actor: "user", occurred_at: "2026-11-06T00:00:00Z", payload: { action: "set_offer" } },
  ],
  new Map([["x", "向山89"]])
);
assert(d.length === 3, "grok event ignored");
assert(d[0].title === "向山89" && d[1].title === "（物件）", "titles");

const s = summarize([...m, ...d]);
assert(s.total === 5 && s.take === 2 && s.ng === 3, `counts ${JSON.stringify(s)}`);
assert(s.reasonRate === 4 / 5, `reason rate ${s.reasonRate}`);
// 物件見送りの yield は2件で共通パターン。資金の buffer は 承認1・取消1 で別物なので出ない
assert(s.patterns.length === 1 && s.patterns[0].tag === "yield" && s.patterns[0].count === 2, `patterns ${JSON.stringify(s.patterns)}`);
assert(s.ruleCandidates.length === 1, "rule candidates");
assert(sortNewest([...m, ...d])[0].key === "d:e4", "newest first");

console.log("kurashiftDecisionLog selftest OK");
