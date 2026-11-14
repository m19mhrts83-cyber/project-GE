import StageProposalActions from "@/components/review/StageProposalActions";
import { loadStageReview, verdictLabel, type StageProposal } from "@/lib/agentStageReview";

/**
 * /review「AI社員の段階」: 週次稼働と判断ログから出した 上げる／戻す 提案を決める場所（サーバー描画）。
 * 見る順: ① 段階ごとの人数 → ② 提案（理由つきで決める） → ③ 見守り（あと何が足りないか）。
 */

function md(iso: string): string {
  const d = new Date(Date.parse(iso) + 9 * 3600_000);
  return Number.isNaN(d.getTime()) ? "—" : `${d.getUTCMonth() + 1}/${d.getUTCDate()}`;
}

function Weeks({ p }: { p: StageProposal }) {
  if (!p.weeks.length) return null;
  return (
    <span className="stg-weeks" aria-label="週次稼働（新しい順）">
      {p.weeks.slice(0, 6).map((w) => (
        <span key={w.day} title={`${md(w.day)} ${w.why}`}>
          {w.signal}
        </span>
      ))}
    </span>
  );
}

export default async function StageReviewSection() {
  const { review, decided } = await loadStageReview();
  return (
    <section id="stage" className="stg">
      <h2 style={{ marginTop: 24 }}>AI社員の段階（設計中 → 運用確認 → 運用）</h2>
      {!review ? (
        <p className="empty">まだ提案がありません。土曜 9:00 の週次稼働の集計のあとに入ります。</p>
      ) : (
        <>
          <p className="sub">
            {review.week}・{md(review.generated_at)} 作成。いま 設計中 {review.counts["設計中"] ?? 0}・運用確認 {review.counts["運用確認"] ?? 0}・運用{" "}
            {review.counts["運用"] ?? 0}。週次稼働の🟢が2週続き、松野さんの見送りが3割以下なら「運用」に上げる提案が出ます。決めた理由は判断ログに残り、来週の提案に効きます。
          </p>
          {review.errors.length ? <p className="empty">{review.errors.join(" ／ ")}</p> : null}
          {review.proposals.length === 0 ? <p className="empty">今週の提案はありません（下の見守りに、あと何が足りないかがあります）。</p> : null}
          {review.proposals.map((p) => {
            const dd = decided[p.key] || null;
            return (
              <article key={p.key} className={`card stg-card ${p.kind}`}>
                <header>
                  <span className="lvl">{p.kind === "down" ? "戻す提案" : "上げる提案"}</span>
                  <strong>
                    {p.id} {p.name}：{p.from} → {p.to}
                  </strong>
                  <Weeks p={p} />
                </header>
                <ul className="stg-why">
                  {p.reasons.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
                <StageProposalActions p={p} decided={dd} />
              </article>
            );
          })}
          {review.watch.length ? (
            <details className="stg-watch">
              <summary className="sub">見守り（まだ条件に届いていない {review.watch.length} 人）</summary>
              <ul>
                {review.watch.map((p) => (
                  <li key={p.key}>
                    <b>
                      {p.id} {p.name}
                    </b>{" "}
                    <span className="sub">
                      {p.from}→{p.to}：{p.blockers.join(" ／ ")}
                      {p.last_decision?.note ? `（前回: ${verdictLabel(p.last_decision.action, p)}・${p.last_decision.note}）` : ""}
                    </span>{" "}
                    <Weeks p={p} />
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </>
      )}
    </section>
  );
}
