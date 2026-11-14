import type { CSSProperties } from "react";
import {
  SIGNAL_LABEL,
  SIGNAL_ORDER,
  deltaOf,
  loadWeeklyActivity,
  md,
  rowValue,
  type ActivityRow,
  type PrevMap,
  type Signal,
} from "@/lib/agentWeeklyActivity";
import MaturityCountUp from "./MaturityCountUp";

/**
 * /agent-team「週次稼働」タブ（サーバー描画）。エラーだけでなく、各AI社員・Grok Bot が今週どれだけ機能したか。
 * 見る順: ① 機能した社員の数と判定の内訳 → ② 次の一手（🔴🟡） → ③ 社員ごとの表（押すと内訳）。
 * 数えるのは土曜 9:00 の scripts/jarvis_agent_weekly_activity.py（314 週次と同時）。
 */

type Vars = CSSProperties & Record<`--${string}`, string | number>;

const SIG_CLASS: Record<Signal, string> = { "🟢": "g", "🟡": "y", "🔴": "r", "⚪": "n" };

function n(v: number | null | undefined): string {
  return v == null ? "—" : String(v);
}

function Delta({ d }: { d: number | null }) {
  if (d == null || d === 0) return null;
  return <i className={`wa-delta ${d > 0 ? "up" : "down"}`}>{d > 0 ? `+${d}` : d}</i>;
}

function SlackChips({ r }: { r: ActivityRow }) {
  if (!r.slack_posts) return <span className="meta">0</span>;
  const sig = r.slack_signals || {};
  return (
    <span className="wa-slack">
      {r.slack_posts}
      <span className="meta">
        {(["🟢", "🟡", "🔴"] as Signal[])
          .filter((s) => sig[s])
          .map((s) => ` ${s}${sig[s]}`)
          .join("")}
      </span>
    </span>
  );
}

function Detail({ r }: { r: ActivityRow }) {
  const bits: string[] = [];
  if (r.ok != null || r.ng != null) bits.push(`OK ${n(r.ok)} ／ NG ${n(r.ng)}`);
  if (r.retries) bits.push(`処理できず再試行 ${r.retries} 回`);
  if (r.pending) bits.push(`受け口に残っている ${r.pending} 件${r.pending_samples?.length ? `（${r.pending_samples.join("、")}）` : ""}`);
  if (r.expected) bits.push(`予定 ${r.expected} 回／週`);
  return (
    <div className="wa-detail">
      {bits.length ? <p>{bits.join(" · ")}</p> : null}
      <p className="meta">
        数えた場所: {r.sources.length ? r.sources.join("・") : "なし"}
        {r.notes.length ? ` · ${r.notes.join(" · ")}` : ""}
      </p>
    </div>
  );
}

function AiTable({ rows, prev }: { rows: ActivityRow[]; prev: PrevMap }) {
  return (
    <div className="at-table-wrap">
      <table className="at-table wa-table">
        <thead>
          <tr>
            <th>社員</th>
            <th>判定</th>
            <th title="トリガーが引かれた回数">起動</th>
            <th title="起動のうち実際に処理した回数">実働</th>
            <th title="処理した物の数（先週比）">件数</th>
            <th>失敗</th>
            <th title="Slack に出した報告（判定の内訳）">報告</th>
            <th>最終</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className={`wa-row s-${SIG_CLASS[r.signal]}`}>
              <td>
                <details>
                  <summary>
                    <b>{r.id}</b> {r.name}
                    <span className="wa-why">{r.why}</span>
                  </summary>
                  <Detail r={r} />
                </details>
              </td>
              <td className="wa-sig" title={SIGNAL_LABEL[r.signal]}>
                {r.signal}
              </td>
              <td>{n(r.runs)}</td>
              <td>{n(r.worked)}</td>
              <td>
                {n(r.items)}
                <Delta d={deltaOf(r, prev)} />
              </td>
              <td className={r.fail ? "wa-bad" : undefined}>{n(r.fail)}</td>
              <td>
                <SlackChips r={r} />
              </td>
              <td>{md(r.last_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function GrokTable({ rows, prev }: { rows: ActivityRow[]; prev: PrevMap }) {
  return (
    <div className="at-table-wrap">
      <table className="at-table wa-table">
        <thead>
          <tr>
            <th>Grok Bot</th>
            <th>判定</th>
            <th title="報告メールの件名で数えた成果物（予定）">成果物</th>
            <th>結論の内訳</th>
            <th>Slack</th>
            <th>最終</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const kinds = Object.entries(r.kinds_expected || {}).map(([k, e]) => `${k} ${r.kinds?.[k] ?? 0}/${e}`);
            const oc = Object.entries(r.outcomes || {}).map(([k, v]) => `${k} ${v}`);
            return (
              <tr key={r.id} className={`wa-row s-${SIG_CLASS[r.signal]}`}>
                <td>
                  <details>
                    <summary>
                      <b>{r.code}</b> {r.name}
                      <span className="wa-why">{r.why}</span>
                    </summary>
                    <Detail r={r} />
                  </details>
                </td>
                <td className="wa-sig" title={SIGNAL_LABEL[r.signal]}>
                  {r.signal}
                </td>
                <td>
                  {kinds.length ? kinds.join(" · ") : "—"}
                  <Delta d={deltaOf(r, prev)} />
                </td>
                <td>{oc.length ? oc.join(" · ") : "—"}</td>
                <td>
                  <SlackChips r={r} />
                </td>
                <td>{md(r.last_at)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default async function WeeklyActivityPanel() {
  const { report, prev, error } = await loadWeeklyActivity();
  if (!report) {
    return (
      <section className="wa">
        {error ? <p className="meta">記録を読めませんでした（{error}）。</p> : null}
        <p className="meta">まだ週次稼働の記録がありません。最初の集計は次の土曜 9:00（314 週次と同時）に入ります。</p>
      </section>
    );
  }
  const s = report.summary;
  const all = [...report.agents, ...report.grok];
  const totalItems = all.reduce((a, r) => a + rowValue(r), 0);
  const order = (r: ActivityRow) => SIGNAL_ORDER.indexOf(r.signal);
  const agents = [...report.agents].sort((a, b) => order(a) - order(b) || a.id.localeCompare(b.id));
  const grok = [...report.grok].sort((a, b) => order(a) - order(b));

  return (
    <section className="wa">
      <div className="wa-hero">
        <div>
          <p className="wa-eyebrow">今週機能したAI社員・Grok Bot</p>
          <p className="wa-big">
            <MaturityCountUp value={report.worked_agents} decimals={0} />
            <small> / {report.total_agents}</small>
          </p>
          <p className="wa-sub">
            {md(report.since)}〜{md(report.until)} · 処理した件数の合計 {totalItems.toLocaleString()} · 毎週土曜 9:00 に更新
          </p>
        </div>
        <ul className="wa-sigs" aria-label="判定の内訳">
          {SIGNAL_ORDER.map((k, i) => (
            <li key={k} className={`s-${SIG_CLASS[k]}`} style={{ "--d": `${i * 120}ms` } as Vars}>
              <span className="wa-sig-n">{s[k] ?? 0}</span>
              <span>
                {k} {SIGNAL_LABEL[k]}
              </span>
            </li>
          ))}
        </ul>
      </div>

      {report.attention.length ? (
        <>
          <h3 className="mx-h">
            次の一手 <span>止まっている・詰まっている順</span>
          </h3>
          <ul className="wa-next">
            {report.attention.slice(0, 8).map((a) => (
              <li key={a.id} className={`s-${SIG_CLASS[a.signal]}`}>
                <b>
                  {a.signal} {a.id.replace("grok:", "Grok ")} {a.name}
                </b>
                <span>{a.why}</span>
              </li>
            ))}
          </ul>
        </>
      ) : null}

      <h3 className="mx-h">
        AI社員 <span>押すと内訳・数えた場所</span>
      </h3>
      <AiTable rows={agents} prev={prev} />

      <h3 className="mx-h">
        Grok Bot <span>Grok 自身では数えられないので、報告メールと Slack の成果物で数えています</span>
      </h3>
      <GrokTable rows={grok} prev={prev} />

      {report.errors.length ? (
        <details className="mat-rule" open>
          <summary>今回読めなかったもの（{report.errors.length}）</summary>
          <ul className="meta">
            {report.errors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </details>
      ) : null}

      <details className="mat-rule">
        <summary>数え方</summary>
        <p className="meta">
          起動＝トリガーが引かれた回数、実働＝そのうち実際に処理した回数、件数＝処理した物の数（点検した下書き・判定した物件など）、報告＝Slack に出した報告の数です。
          🔴 は予定があるのに動いた跡がない・失敗が3割以上、🟡 は詰まり（処理できず再試行・受け口に残ったまま）・失敗あり・起動が予定の6割未満、🟢 は回っている（処理対象がない週の空振りも含む）です。
          社員ごとの数える場所は config/agent_weekly_activity.yaml。🟡 は週次まとめ（314 の土曜 Slack）にも載ります。
        </p>
      </details>
    </section>
  );
}
