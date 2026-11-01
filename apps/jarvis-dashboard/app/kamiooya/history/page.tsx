import Link from "next/link";
import Shell from "@/components/Shell";
import { createClient } from "@/lib/supabase/server";
import { parseWorkHistory, workTotals, type WorkHistory } from "@/lib/kamiooyaWorkHistory";

export const dynamic = "force-dynamic";

const statusLabels: Record<string, string> = { planned: "予定", running: "作業中", waiting: "確認待ち", done: "完了" };
const kindLabels: Record<string, string> = { log: "実行記録", note: "運用メモ", ask: "質問", answer: "本人回答", "add-item": "項目追加" };
const timeLabels: Record<string, string> = { unrecorded: "時間未記録", owner_confirmed: "本人確認済み", estimated: "推計", agent_elapsed: "エージェント処理" };
const date = (raw: string | null) => raw && !Number.isNaN(Date.parse(raw))
  ? new Intl.DateTimeFormat("ja-JP", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Tokyo" }).format(new Date(raw)) : "未記録";

export default async function HistoryPage({ searchParams }: { searchParams: Promise<{ q?: string; project?: string }> }) {
  const params = await searchParams;
  const q = typeof params.q === "string" ? params.q.trim() : "";
  const projectId = typeof params.project === "string" ? params.project : "";
  const supabase = await createClient();
  const { data: user } = await supabase.auth.getUser();
  if (!user.user) return <Shell active="/kamiooya"><p>ログインして作業履歴を確認してください。</p></Shell>;
  const { data, error } = await supabase.from("sync_meta").select("value").eq("key", "kamiooya_work_history").maybeSingle();
  let history: WorkHistory | null = null;
  let failure = error ? "作業履歴を取得できませんでした。再読み込みしてください。" : "";
  try { history = parseWorkHistory(data?.value); } catch { failure = "保存された作業履歴の形式を確認してください。"; }
  const projects = (history?.projects ?? []).filter(p => !projectId || p.id === projectId);
  return (
    <Shell active="/kamiooya">
      <Link href="/kamiooya">← 神大家運営</Link>
      <h1>作業項目と履歴</h1>
      <p className="sub">事前に相談した項目ごとに、実行結果と質問・回答を振り返れます。時間未記録・推計・本人確認済みを区別しています。</p>
      <p className="meta">記録の最終更新: {date(history?.updated_at ?? null)}</p>
      <form method="get" style={{ display: "flex", flexWrap: "wrap", gap: 8, margin: "16px 0" }}>
        <label>案件 <select name="project" defaultValue={projectId}><option value="">すべて</option>{(history?.projects ?? []).map(p => <option key={p.id} value={p.id}>{p.title}</option>)}</select></label>
        <label>検索 <input name="q" defaultValue={q} placeholder="作業項目・記録の内容" /></label>
        <button className="btn" type="submit">絞り込む</button>
      </form>
      {failure ? <p role="alert">{failure}</p> : !history ? <p className="empty">まだ同期された記録がありません。</p> : projects.length === 0 ? <p>該当する案件がありません。</p> : null}
      {projects.map(p => {
        const totals = workTotals(p.events);
        const pending = p.events.filter(e => e.kind === "ask" && !p.events.some(a => a.kind === "answer" && a.question_id === e.id));
        const items = p.items.filter(i => !q || i.title.includes(q) || p.events.some(e => e.item_id === i.id && e.summary.includes(q)));
        return <section className="home-section" key={p.id}>
          <h2>{p.title}</h2>
          <p className="meta">当初見積: {p.estimate_minutes == null ? "未記録" : `${p.estimate_minutes}分`} · {p.items.filter(i => i.status === "done").length}/{p.items.length}項目完了 · 未回答 {pending.length}件</p>
          <p>本人確認済み {totals.confirmed}分 · 推計 {totals.estimated}分 · エージェント処理 {totals.agent}分 · 時間未記録 {totals.unrecorded}件</p>
          <p className="meta">時間の合算を請求額とは扱いません。見積は作業時間の実績ではありません。</p>
          {!items.length ? <p>一致する作業項目がありません。</p> : null}
          {items.map(i => {
            const events = p.events.filter(e => e.item_id === i.id).sort((a, b) => b.at.localeCompare(a.at));
            const open = pending.some(e => e.item_id === i.id) || i.status === "running";
            return <details className="card" key={i.id} open={open || undefined} style={{ marginBottom: 12, padding: 14 }}>
              <summary style={{ cursor: "pointer", fontWeight: 600 }}>{statusLabels[i.status] ?? i.status} · {i.title} <span className="meta">（履歴 {events.length}件）</span></summary>
              {!events.length ? <p className="meta">実行記録はまだありません。</p> : null}
              <ol style={{ paddingLeft: 22 }}>
                {events.map(e => <li key={e.id} style={{ margin: "16px 0", overflowWrap: "anywhere" }}>
                  <div className="meta">記録: {date(e.at)} · {e.actor} · {kindLabels[e.kind] ?? e.kind}{e.kind === "ask" ? pending.some(x => x.id === e.id) ? " · 回答待ち" : " · 回答記録済み" : ""}</div>
                  <p style={{ whiteSpace: "pre-wrap", margin: "6px 0" }}>{e.summary}</p>
                  <span className="meta">{timeLabels[e.time_kind] ?? "時間の種別未確認"}{e.minutes == null ? "" : ` ${e.minutes}分`}</span>
                  {events.some(x => x.supersedes === e.id) ? <div className="meta">訂正後の記録があります（時間の集計対象外）</div> : null}
                  {e.question_id ? <div className="meta">対応する質問: {e.question_id}</div> : null}
                  {e.evidence.filter(url => typeof url === "string" && url.startsWith("https://")).map((url, n) => <div key={n}><a href={url} target="_blank" rel="noreferrer">根拠・成果物 {n + 1} ↗</a></div>)}
                </li>)}
              </ol>
            </details>;
          })}
        </section>;
      })}
    </Shell>
  );
}
