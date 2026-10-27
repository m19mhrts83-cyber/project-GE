/**
 * Run: npx tsx lib/reViewingGate.selftest.ts
 */
import { filterViewingBoardDeals, viewingNextStep } from "./reDealStages";
import { deskGate, offerLineMan, parseConservativeRentMan, viewingPace } from "./reViewingGate";

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg);
}

// 想定家賃テキスト（本番の S3 の書き方）から保守側を取る
assert(parseConservativeRentMan("本線**5.5万**／保守**5.0万**（レンジ5.0–6.0万）") === 5, "保守");
assert(parseConservativeRentMan("机上6.0万（表面18.94%）。入居付け本線 **5.0–5.5万**") === 5, "range low");
assert(parseConservativeRentMan("６．５万") === 6.5, "全角");
assert(parseConservativeRentMan("") === null, "empty");
assert(parseConservativeRentMan("要確認") === null, "no number");

// 指値ライン = 家賃×12÷0.15 − 修繕
assert(offerLineMan(5) === 400, "line 5万");
assert(offerLineMan(5, 80) === 320, "line minus repair");

const hold = (rent: string, extra: Record<string, unknown> = {}) => ({
  s3_investigation: { verdict: "hold", expected_rent: rent },
  ...extra,
});

// 豊川市伊奈町: 掲載380万・保守5.0万 → 机上GO
const g1 = deskGate({ status: "viewing", price_man: "380.0", summary_json: hold("入居付け本線 **5.0–5.5万**") });
assert(g1.verdict === "go" && g1.lineMan === 400, `go: ${JSON.stringify(g1)}`);

// 掲載2780万・保守5.0万 → 指値ライン超え
const g2 = deskGate({ status: "viewing", price_man: 2780, summary_json: hold("本線5.5万／保守5.0万") });
assert(g2.verdict === "over" && g2.cutPct === 86, `over: ${JSON.stringify(g2)}`);

// 手入力の家賃と修繕が S3 より優先
const g3 = deskGate({
  status: "viewing",
  price_man: 380,
  summary_json: hold("5.0–5.5万", { viewing: { desk_rent_man: 4.5, repair_man: 50 } }),
});
assert(g3.rentSource === "manual" && g3.lineMan === 310 && g3.verdict === "over", `manual: ${JSON.stringify(g3)}`);

// 家賃なし → unknown
assert(deskGate({ status: "info", price_man: 500, summary_json: hold("") }).verdict === "unknown", "unknown");

// ボード: 机上GO の hold が S3 go より上に来る
const board = filterViewingBoardDeals([
  { id: "s3go", status: "info", price_man: 900, summary_json: { s3_investigation: { verdict: "go" } } },
  { id: "deskgo", status: "info", price_man: 380, summary_json: hold("5.0–5.5万") },
  { id: "plainhold", status: "info", price_man: 380, summary_json: hold("") },
]);
assert(board.map((d) => d.id).join(",") === "deskgo,s3go,plainhold", `board: ${board.map((d) => d.id)}`);

// 次にやること: 机上GO は内見依頼を促す
const next = viewingNextStep({ status: "info", price_man: 380, summary_json: hold("5.0–5.5万") });
assert(next.urgent && next.label.includes("内見依頼"), `next: ${next.label}`);

// ペース: 今月の内見日と机上GO候補を数える
const pace = viewingPace(
  [
    { status: "info", price_man: 380, summary_json: hold("5.0万") },
    { status: "viewing", summary_json: { viewing: { step: "scheduled", date: "2026-10-30" } } },
    { status: "viewing", summary_json: { viewing: { step: "scheduled", date: "2026-11-02" } } },
  ],
  "2026-10-27"
);
assert(pace.goCandidates === 1 && pace.thisMonth === 1, `pace: ${JSON.stringify(pace)}`);
assert(pace.candidatesShort === 2 && pace.monthShort === 1, "pace short");

console.log("reViewingGate selftest OK");
