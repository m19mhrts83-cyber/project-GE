import { WESTUDY_FORUM_URLS } from "@/lib/glucon/types";
import type {
  GluconArchiveKindView,
  GluconArchiveMonth,
} from "@/lib/glucon/stats";
import type { GluconDraftStatus } from "@/lib/glucon/types";

function statusLabel(status: GluconDraftStatus): string {
  switch (status) {
    case "posted":
      return "投稿済";
    case "skipped":
      return "スキップ";
    case "queued":
      return "投稿待ち";
    case "failed":
      return "失敗";
    case "ready":
      return "準備済";
    default:
      return "下書き";
  }
}

function KindBlock({
  label,
  view,
}: {
  label: string;
  view: GluconArchiveKindView | null;
}) {
  if (!view) {
    return (
      <section className="glucon-archive-kind">
        <h3>{label}</h3>
        <p className="meta">この月の記録はありません</p>
      </section>
    );
  }
  const forumUrl = WESTUDY_FORUM_URLS[view.kind];
  return (
    <section className="glucon-archive-kind">
      <h3>
        {label}
        <span className="meta">（{statusLabel(view.status)}）</span>
      </h3>
      {view.kind === "result" && view.estimatedPoints > 0 ? (
        <p className="meta">目安 {view.estimatedPoints} 点</p>
      ) : null}
      {view.status === "posted" ? (
        <p className="meta">
          <a href={forumUrl} target="_blank" rel="noreferrer">
            WeStudy で見る
          </a>
        </p>
      ) : null}
      {view.body.trim() ? (
        <pre className="glucon-archive-body">{view.body}</pre>
      ) : (
        <p className="meta">本文なし</p>
      )}
    </section>
  );
}

export default function GluconArchiveList({
  months,
}: {
  months: GluconArchiveMonth[];
}) {
  return (
    <section className="glucon-archive" aria-labelledby="glucon-archive-heading">
      <h2 id="glucon-archive-heading">これまでの報告</h2>
      <p className="meta">
        投稿した活動・成果の本文です。クリックで開きます。知見のベースとして残します。
      </p>
      {!months.length ? (
        <p className="meta">初回投稿後にここに溜まります</p>
      ) : (
        months.map((m) => {
          const bits = [
            m.activity ? `活動 ${statusLabel(m.activity.status)}` : null,
            m.result ? `成果 ${statusLabel(m.result.status)}` : null,
            m.estimatedPoints > 0 ? `目安 ${m.estimatedPoints} 点` : null,
          ].filter(Boolean);
          return (
            <details key={m.periodKey} className="card watch-fold">
              <summary className="watch-fold-summary">
                <header className="watch-fold-head">
                  <strong>{m.periodKey}</strong>
                  <span className="meta">{bits.join(" ／ ")}</span>
                  <span className="watch-fold-chevron" aria-hidden>
                    開く
                  </span>
                </header>
              </summary>
              <div className="watch-fold-body">
                <KindBlock label="活動報告" view={m.activity} />
                <KindBlock label="成果報告" view={m.result} />
              </div>
            </details>
          );
        })
      )}
    </section>
  );
}
