import Link from "next/link";
import type { GluconMaterialItem } from "@/lib/glucon/grokMaterials";
import type { GluconDraftRow } from "@/lib/glucon/types";
import { skipGluconMaterialForm } from "@/app/actions/glucon";

function statusLabel(status: string): string {
  switch (status) {
    case "pending":
      return "未使用";
    case "used":
      return "使用済";
    case "skipped":
      return "スキップ";
    case "cycle_closed":
      return "周期終了";
    default:
      return status;
  }
}

function draftStatusLabel(status: string): string {
  switch (status) {
    case "posted":
      return "投稿済";
    case "ready":
      return "準備済";
    case "skipped":
      return "スキップ";
    default:
      return "下書き";
  }
}

function MaterialRow({ item }: { item: GluconMaterialItem }) {
  return (
    <details className="glucon-material-row">
      <summary>
        <span className="glucon-material-title">{item.title}</span>
        <span className="meta">
          {item.period_key || "—"} · {statusLabel(item.status)} ·{" "}
          {item.recorded_at || "—"} · {item.source}
        </span>
      </summary>
      <pre className="glucon-material-body">{item.body || "（本文なし）"}</pre>
      {item.status === "pending" ? (
        <form action={skipGluconMaterialForm}>
          <input type="hidden" name="id" value={item.id} />
          <button type="submit" className="btn-secondary btn-sm">
            スキップ
          </button>
        </form>
      ) : null}
    </details>
  );
}

function DraftBlock({ draft }: { draft: GluconDraftRow }) {
  return (
    <details className="glucon-material-draft">
      <summary>
        <span>{draft.period_key} 下書き</span>
        <span className="meta">（{draftStatusLabel(draft.status)}）</span>
      </summary>
      {draft.body?.trim() ? (
        <pre className="glucon-archive-body">{draft.body}</pre>
      ) : (
        <p className="meta">本文なし</p>
      )}
    </details>
  );
}

export default function GluconMaterialsList({
  tab,
  materials,
  drafts,
  periodKeys,
  periodKey,
  status,
}: {
  tab: "activity" | "result";
  materials: GluconMaterialItem[];
  drafts: GluconDraftRow[];
  periodKeys: string[];
  periodKey?: string;
  status?: string;
}) {
  const base = `/glucon/materials?tab=${tab}`;

  return (
    <div className="glucon-materials-page">
      <nav className="glucon-materials-tabs">
        <Link
          href="/glucon/materials?tab=activity"
          className={tab === "activity" ? "active" : undefined}
        >
          活動
        </Link>
        <Link
          href="/glucon/materials?tab=result"
          className={tab === "result" ? "active" : undefined}
        >
          成果
        </Link>
        <Link href="/glucon" className="meta-link">
          ← グルコン報告
        </Link>
      </nav>

      <form className="glucon-materials-filters" method="get">
        <input type="hidden" name="tab" value={tab} />
        <label>
          月次キー
          <select name="period_key" defaultValue={periodKey || ""}>
            <option value="">すべて</option>
            {periodKeys.map((pk) => (
              <option key={pk} value={pk}>
                {pk}
              </option>
            ))}
          </select>
        </label>
        <label>
          状態
          <select name="status" defaultValue={status || ""}>
            <option value="">すべて</option>
            <option value="pending">未使用</option>
            <option value="used">使用済</option>
            <option value="skipped">スキップ</option>
            <option value="cycle_closed">周期終了</option>
          </select>
        </label>
        <button type="submit">絞り込み</button>
      </form>

      <section>
        <h2>Grok 材料（{materials.length}件）</h2>
        <p className="meta">
          グルコン未投稿の月も参照可。周期終了（cycle_closed）後は下書き生成に載りません。
        </p>
        {materials.length ? (
          materials.map((m) => <MaterialRow key={m.id} item={m} />)
        ) : (
          <p className="meta">該当する材料はありません</p>
        )}
      </section>

      <section>
        <h2>下書き（{drafts.length}件）</h2>
        <p className="meta">draft / ready 含む未投稿下書きもここで確認できます。</p>
        {drafts.length ? (
          drafts.map((d) => (
            <DraftBlock key={`${d.period_key}-${d.kind}`} draft={d} />
          ))
        ) : (
          <p className="meta">該当する下書きはありません</p>
        )}
      </section>

      {(periodKey || status) && (
        <p className="meta">
          <Link href={base}>フィルタをクリア</Link>
        </p>
      )}
    </div>
  );
}
