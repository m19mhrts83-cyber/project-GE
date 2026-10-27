/**
 * Run: npx tsx lib/reDealStages.selftest.ts
 */
import {
  acquisitionNextStep,
  applyProgress,
  filterViewingBoardDeals,
  getAcquisition,
  viewingNextStep,
} from "./reDealStages";

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg);
}

const NOW = "2026-10-27T00:00:00Z";
const s3 = (verdict: string) => ({ s3_investigation: { verdict } });

// 内見ボード: S3 go/hold と内見中が載り、pass・見送り済・買付以降は載らない
const board = filterViewingBoardDeals([
  { id: "a", status: "info", summary_json: s3("hold") },
  { id: "b", status: "info", summary_json: s3("go") },
  { id: "c", status: "info", summary_json: s3("pass") },
  { id: "d", status: "viewing", summary_json: { viewing: { step: "scheduled", date: "2026-11-02" } } },
  { id: "e", status: "viewing", summary_json: { viewing: { step: "scheduled", date: "2026-10-29" } } },
  { id: "f", status: "offer", summary_json: s3("go") },
  { id: "g", status: "info", summary_json: { ...s3("go"), viewing: { verdict: "go" } } },
  { id: "h", status: "viewing", summary_json: { viewing: { step: "done" } } },
]);
assert(board.map((d) => d.id).join(",") === "e,d,h,b,a", `board order: ${board.map((d) => d.id)}`);

// 次にやること
assert(
  viewingNextStep({ status: "viewing", summary_json: { viewing: { step: "scheduled", date: "2026-10-29" } } }, "2026-10-27").label.includes("あと2日"),
  "days until"
);
assert(
  viewingNextStep({ status: "viewing", summary_json: { viewing: { step: "scheduled", date: "2026-10-20" } } }, "2026-10-27").urgent,
  "past date urgent"
);

// 内見日を入れると日程確定・status=viewing
let r = applyProgress({ status: "info", summary_json: s3("go") }, { kind: "viewing", patch: { date: "2026-11-01" } }, NOW);
assert(r.ok && r.status === "viewing", "date → viewing");
assert(r.ok && (r.summary_json.viewing as { step: string }).step === "scheduled", "date → scheduled");

// 見送り
r = applyProgress({ status: "viewing", summary_json: {} }, { kind: "viewing", patch: { verdict: "pass", step: "done" } }, NOW);
assert(r.ok && r.status === "passed", "verdict pass → passed");

// 不正値
r = applyProgress({ status: "info", summary_json: {} }, { kind: "viewing", patch: { date: "11/1" } }, NOW);
assert(!r.ok, "bad date rejected");

// チェックリストはマージ
r = applyProgress(
  { status: "viewing", summary_json: { viewing: { checklist: { tools: true } } } },
  { kind: "viewing", patch: { checklist: { memo_saved: true } } },
  NOW
);
assert(r.ok && (r.summary_json.viewing as { checklist: Record<string, boolean> }).checklist.tools, "checklist merge");

// 買付開始 → offer / offer_prep
r = applyProgress({ status: "viewing", summary_json: {} }, { kind: "start_acquisition" }, NOW);
assert(r.ok && r.status === "offer", "start → offer");
assert(r.ok && getAcquisition({ status: r.status, summary_json: r.summary_json }).stage === "offer_prep", "offer_prep");

// 段階 → status 連動
r = applyProgress({ status: "offer", summary_json: {} }, { kind: "acquisition", patch: { stage: "contract" } }, NOW);
assert(r.ok && r.status === "loan", "contract → loan");
r = applyProgress({ status: "loan", summary_json: {} }, { kind: "acquisition", patch: { stage: "handover" } }, NOW);
assert(r.ok && r.status === "purchased", "handover → purchased");
r = applyProgress({ status: "offer", summary_json: {} }, { kind: "acquisition", patch: { stage: "bogus" as never } }, NOW);
assert(!r.ok, "bad stage rejected");

// 旧データ（status だけ loan）
assert(getAcquisition({ status: "loan", summary_json: {} }).stage === "loan_applied", "legacy loan");

// 次の一手: 未完チェック → 全部済なら次段階
const nx = acquisitionNextStep({ status: "offer", summary_json: { acquisition: { stage: "offer_submitted", checklist: { "offer_submitted.offer_doc": true } } } });
assert(nx.label.includes("仲介へ提出"), `next open item: ${nx.label}`);
const nx2 = acquisitionNextStep({
  status: "offer",
  summary_json: {
    acquisition: {
      stage: "offer_accepted",
      checklist: { "offer_accepted.accepted": true, "offer_accepted.docs_request": true, "offer_accepted.s7_request": true },
    },
  },
});
assert(nx2.label === "融資申込へ進める" && nx2.urgent, `advance: ${nx2.label}`);

console.log("reDealStages selftest OK");
