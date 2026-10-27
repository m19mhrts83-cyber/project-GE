import Link from "next/link";
import {
  VIEWING_CHECKLIST,
  VIEWING_STEP_LABEL,
  checklistProgress,
  daysUntil,
  getViewing,
  todayJst,
  viewingNextStep,
} from "@/lib/reDealStages";
import { VIEWING_PACE, deskGate, viewingPace } from "@/lib/reViewingGate";

type BoardDeal = {
  id: string;
  title: string;
  status: string;
  area?: string | null;
  price_man?: number | null;
  summary_json?: Record<string, unknown> | null;
  href: string;
};

function verdictOf(d: BoardDeal): string {
  const s3 = d.summary_json?.s3_investigation;
  if (s3 && typeof s3 === "object") {
    return String((s3 as Record<string, unknown>).verdict || "").toUpperCase();
  }
  return "";
}

/**
 * 内見ボード: 「内見に行く物件」を一覧し、次にやることを1行で出す。
 * 並びと対象は lib/reDealStages の filterViewingBoardDeals。
 */
export default function ViewingBoardSection({ deals }: { deals: BoardDeal[] }) {
  if (deals.length === 0) return null;
  const today = todayJst();
  const scheduled = deals.filter((d) => getViewing(d).step === "scheduled").length;
  const undecided = deals.filter((d) => getViewing(d).step === "done").length;
  const pace = viewingPace(deals, today);
  return (
    <div
      className="card"
      id="viewing-board"
      style={{ marginBottom: 16, borderColor: "#38bdf8", background: "#f0f9ff" }}
    >
      <header>
        <span className="lvl">内見</span>
        <strong>
          内見ボード（{deals.length}件 · 日程確定 {scheduled} · 結果待ち {undecided}）
        </strong>
      </header>
      <p className="meta" style={{ marginTop: 6, marginBottom: 8 }}>
        S3 判定が GO／HOLD の物件と、内見を進めている物件。内見GOは「机上で否定材料がない」で出し、室内・傾き・駐車可否・成約家賃は内見で確かめます。指値ライン＝保守の想定家賃×12÷15%−修繕概算。
      </p>
      <div
        style={{
          fontSize: 12,
          fontWeight: 600,
          marginBottom: 8,
          color: pace.candidatesShort || pace.monthShort ? "#92400e" : "#166534",
        }}
      >
        ペース: 机上GOの内見候補 {pace.goCandidates}/{VIEWING_PACE.candidates}件 · 今月の内見{" "}
        {pace.thisMonth}/{VIEWING_PACE.perMonth}件
        {pace.monthShort > 0 ? `（あと${pace.monthShort}件、内見依頼を出す）` : ""}
      </div>
      <div style={{ display: "grid", gap: 8 }}>
        {deals.map((d) => {
          const v = getViewing(d);
          const next = viewingNextStep(d, today);
          const prog = checklistProgress(VIEWING_CHECKLIST, v.checklist);
          const verdict = verdictOf(d);
          const n = v.date ? daysUntil(v.date, today) : NaN;
          const gate = deskGate(d);
          return (
            <div
              key={`vb-${d.id}`}
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: 8,
                alignItems: "center",
                justifyContent: "space-between",
                background: "#fff",
                border: `1px solid ${next.urgent ? "#f59e0b" : "#bae6fd"}`,
                borderRadius: 6,
                padding: "8px 10px",
              }}
            >
              <div style={{ minWidth: 0, flex: "1 1 240px" }}>
                <div style={{ fontSize: 12 }}>
                  <strong>{VIEWING_STEP_LABEL[v.step || "candidate"]}</strong>
                  {v.date ? (
                    <span style={{ marginLeft: 6 }}>
                      📅 {v.date}
                      {v.time ? ` ${v.time}` : ""}
                      {Number.isFinite(n) && n >= 0 ? `（あと${n}日）` : ""}
                    </span>
                  ) : null}
                  {verdict ? (
                    <span className="meta" style={{ marginLeft: 6 }}>
                      S3: {verdict}
                    </span>
                  ) : null}
                  {v.verdict === "hold" ? (
                    <span className="meta" style={{ marginLeft: 6 }}>保留</span>
                  ) : null}
                  <span className="meta" style={{ marginLeft: 6 }}>
                    チェック {prog.done}/{prog.total}
                  </span>
                </div>
                <div style={{ fontWeight: 600, overflowWrap: "anywhere" }}>
                  {d.title}
                </div>
                <div className="meta">
                  {d.area || "—"}
                  {d.price_man != null ? ` · ${d.price_man}万円` : ""}
                  {gate.lineMan != null ? ` · 指値ライン ${gate.lineMan}万円` : ""}
                  {gate.verdict === "go" ? (
                    <span style={{ marginLeft: 6, color: "#166534", fontWeight: 600 }}>机上GO</span>
                  ) : null}
                </div>
                <div
                  style={{
                    fontSize: 12,
                    marginTop: 2,
                    color: next.urgent ? "#92400e" : "#0369a1",
                    fontWeight: 600,
                  }}
                >
                  ▶ {next.label}
                </div>
              </div>
              <Link href={d.href} className="btn">
                開く
              </Link>
            </div>
          );
        })}
      </div>
    </div>
  );
}
