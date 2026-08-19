import type { ReactNode } from "react";
import Link from "next/link";
import { fmtPct, fmtYen, fmtYenSigned } from "@/lib/format";
import type { HouseholdBsSummary } from "@/lib/householdBsInsights";

function toneColor(status: HouseholdBsSummary["cashStatus"]): string | undefined {
  if (status === "要資金調達") return "var(--high)";
  if (status === "注意") return "var(--warn)";
  return "var(--ok)";
}

function SummaryStat({
  label,
  value,
  note,
}: {
  label: string;
  value: string;
  note?: ReactNode;
}) {
  return (
    <div className="card" style={{ minWidth: 220, flex: 1 }}>
      <header>
        <span className="lvl">キャッシュ</span>
        <strong>{label}</strong>
      </header>
      <p style={{ fontSize: "1.1rem", fontWeight: 700, margin: "10px 0 4px" }}>{value}</p>
      {note ? (
        <p className="meta" style={{ margin: 0 }}>
          {note}
        </p>
      ) : null}
    </div>
  );
}

export default function HouseholdBsSummaryPanel({
  summary,
}: {
  summary: HouseholdBsSummary;
}) {
  return (
    <div style={{ marginTop: 12 }}>
      <div className="card">
        <header>
          <span className="lvl">司令塔</span>
          <strong>Cash is King サマリー</strong>
        </header>
        <p className="meta" style={{ marginTop: 6 }}>
          まずキャッシュ土台、その次に資産化、そのうえで必要なら資金調達を見る順番です。
        </p>
        <div
          style={{
            marginTop: 10,
            display: "inline-block",
            padding: "6px 10px",
            borderRadius: 999,
            border: `1px solid ${toneColor(summary.cashStatus) ?? "var(--border)"}`,
            color: toneColor(summary.cashStatus),
            fontWeight: 700,
          }}
        >
          現在の状態: {summary.cashStatus}
        </div>
        <p className="meta" style={{ marginTop: 8 }}>
          {summary.fundingNote}
        </p>
      </div>

      <div className="mq-dual" style={{ marginTop: 12, gap: 12 }}>
        <SummaryStat
          label="現金土台"
          value={fmtYen(summary.cashTotalJpy)}
          note={`次物件キープ ${fmtYen(summary.nextPropertyJpy)} / 引落・ブリッジ ${fmtYen(summary.bridgeNeedJpy)}`}
        />
        <SummaryStat
          label="防衛後の余力"
          value={fmtYen(summary.deployableCashJpy)}
          note={
            summary.fundingGapJpy > 0
              ? `不足 ${fmtYen(summary.fundingGapJpy)}`
              : "ここから投資・返済・保留を考える"
          }
        />
        <SummaryStat
          label="ポケット入金"
          value={fmtYen(summary.pocketIncomeJpy)}
          note={`収入全体に占める比率 ${fmtPct(summary.pocketIncomeRatio)}`}
        />
      </div>

      <div className="mq-dual" style={{ marginTop: 12, gap: 12 }}>
        <SummaryStat
          label="今年のキャッシュ収支"
          value={fmtYenSigned(summary.netFlowJpy)}
          note="収入 − 支出。プラスなら現金を積み上げやすい"
        />
        <SummaryStat
          label="純資産前年差"
          value={fmtYenSigned(summary.netWorthDeltaJpy)}
          note={`現在の純資産 ${fmtYen(summary.netWorthJpy)}`}
        />
        <SummaryStat
          label="投資の受け皿"
          value={fmtYen(summary.coreAssetJpy + summary.themeAssetJpy)}
          note={
            <>
              コア {fmtYen(summary.coreAssetJpy)} / Theme {fmtYen(summary.themeAssetJpy)}
              {" · "}
              <Link href="/portfolio">配分を見る</Link>
            </>
          }
        />
      </div>

      <p className="meta" style={{ marginTop: 8 }}>
        判断導線: <Link href="/portfolio">どこへ回すか</Link> ·{" "}
        <Link href="/money-ops">今月事故らないか</Link> ·{" "}
        <Link href="/lifeplan/analyze">5年続けてよいか</Link>
      </p>
    </div>
  );
}
