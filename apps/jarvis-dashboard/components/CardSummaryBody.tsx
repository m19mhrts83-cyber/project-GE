import {
  parseDigestSummary,
  splitInlineBold,
} from "@/lib/digestSummary";

function RichText({ text }: { text: string }) {
  return (
    <>
      {splitInlineBold(text).map((p, i) =>
        p.bold ? <strong key={i}>{p.text}</strong> : <span key={i}>{p.text}</span>,
      )}
    </>
  );
}

/** digest / 通常カードの要約表示 */
export default function CardSummaryBody({
  kind,
  summary,
  payload,
}: {
  kind: string;
  summary: string | null;
  payload?: Record<string, unknown> | null;
}) {
  if (kind !== "digest") {
    return summary ? <p className="sum">{summary}</p> : null;
  }

  const parsed = parseDigestSummary(summary, payload);
  if (!parsed.question && !parsed.bullets.length) {
    return summary ? <p className="sum digest-sum-fallback">{summary}</p> : null;
  }

  return (
    <div className="digest-body">
      {parsed.question ? (
        <p className="digest-question">{parsed.question}</p>
      ) : null}
      {parsed.bullets.length > 0 ? (
        <>
          <p className="digest-list-label">候補メモ</p>
          <ul className="digest-list">
            {parsed.bullets.map((b, i) => (
              <li key={`${b.title}-${i}`}>
                <div className="digest-item-title">
                  <RichText text={b.title} />
                </div>
                {b.detail ? (
                  <div className="digest-item-detail">
                    <RichText text={b.detail} />
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}
