/**
 * Run: npx tsx lib/kurashiftDecisionLog.selftest.ts
 */
import { appendMoneyDecision, parseDecisionNote } from "./kurashiftDecision";
import { parseRetro } from "./kurashiftDecision";
import {
  buildHints,
  dealRows,
  moneyRows,
  retroCandidates,
  sortNewest,
  summarize,
  summarizeRetro,
  toAiBrief,
} from "./kurashiftDecisionLog";

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

// 判断メモの付帯情報（時間・候補・前回と同じ）
const n2 = parseDecisionNote({ decide_ms: 4200.4, suggested_tags: ["yield", "x"], same_as_last: true });
assert(n2!.decide_ms === 4200 && n2!.suggested_tags!.length === 1 && n2!.same_as_last === true, "extras");
assert(parseDecisionNote({ decide_ms: 7 * 3600_000 })!.decide_ms === null, "left open → not counted");
assert(parseRetro({ quality: "regret", note: " x " })!.note === "x" && parseRetro({ quality: "bad" }) === null, "retro parse");

// ヒント: 同じ種類の過去の判断だけを引く。よく使う理由が先、前回は理由のあるもの
const hist = [
  ...moneyRows([
    {
      id: "a",
      title: "積立",
      kind: "broker_transfer",
      assist_payload: {
        decision_log: [
          { at: "2026-09-01T00:00:00Z", to: "approved", reason_tags: ["plan_fit"], retro: { at: "2026-09-20T00:00:00Z", quality: "regret", note: "金額を確かめる" } },
          { at: "2026-10-01T00:00:00Z", to: "approved", reason_tags: ["plan_fit", "buffer"], note: "6か月分残す", scope: "always" },
          { at: "2026-10-20T00:00:00Z", to: "approved" },
          { at: "2026-10-21T00:00:00Z", to: "done" },
          { at: "2026-10-22T00:00:00Z", to: "cancelled", reason_tags: ["timing"] },
        ],
      },
    },
  ]),
  ...dealRows(
    [
      { id: "v1", deal_id: "x", event_type: "status_change", actor: "user", occurred_at: "2026-10-01T00:00:00Z", payload: { action: "set_viewing" } },
      { id: "r1", deal_id: "x", event_type: "note", actor: "user", occurred_at: "2026-10-30T00:00:00Z", payload: { action: "retro", ref_event_id: "v1", quality: "good" } },
      { id: "c1", deal_id: "x", event_type: "review_confirm", actor: "user", occurred_at: "2026-09-01T00:00:00Z", payload: { action: "confirm" } },
    ],
    new Map()
  ),
];
const h = buildHints(hist, "money:approved");
assert(h.count === 3, `hint count ${h.count}`);
assert(h.tagCounts[0].key === "plan_fit" && h.tagCounts[0].count === 2, "most used first");
assert(h.last?.at === "2026-10-01T00:00:00Z" && h.last.note === "6か月分残す", "last = newest with a reason");
assert(h.alwaysTags.includes("buffer") && h.alwaysTags.includes("plan_fit"), "always tags");
assert(h.regrets.length === 1 && h.regrets[0].note === "金額を確かめる", "regret shown before deciding");
assert(buildHints(hist, "money:cancelled").tagCounts[0].key === "timing", "ctx separated");
assert(buildHints(hist, "deal:pass").last === null, "no history → no last");

// 答え合わせ: 14日たった「承認・内見・買付」だけ。完了・候補に残す・答え合わせ済みは出さない
const wait = retroCandidates(hist, new Date("2026-11-10T00:00:00Z"));
assert(wait.length === 2, `retro candidates ${wait.map((r) => r.key).join(",")}`);
assert(wait.every((r) => r.ctx === "money:approved"), "only decisions themselves");
const rs = summarizeRetro(hist);
assert(rs.total === 2 && rs.good === 1 && rs.regret === 1, "retro summary");

// AI に渡す文章: 件数に合った頼み方・表の区切りを壊さない
const brief = toAiBrief(hist);
assert(brief.includes("空欄を推測で埋めないでください") && brief.includes("参照例として"), "stage wording");
assert(brief.includes("やり直したい：金額を確かめる"), "retro in brief");
assert(!toAiBrief([{ ...hist[0], note: "a|b" }]).includes("a|b"), "pipe escaped");

console.log("kurashiftDecisionLog selftest OK");
