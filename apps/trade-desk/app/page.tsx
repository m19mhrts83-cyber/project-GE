import Shell from "@/components/Shell";
import EnqueueJobButton from "@/components/EnqueueJobButton";
import { createClient } from "@/lib/supabase/server";
import { fmtYen } from "@/lib/format";
import {
  annualNoticeCopy,
  isAnnualLifeplanWindow,
} from "@/lib/lifeplanNotices";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const [
    { data: accounts },
    { data: snaps },
    { data: themes },
    { data: research },
    { data: consults },
    { data: annualDone },
  ] = await Promise.all([
    supabase
      .from("portfolio_accounts")
      .select("id, name, kind")
      .eq("active", true),
    supabase
      .from("portfolio_snapshots")
      .select("account_id, as_of, value_jpy, source")
      .order("as_of", { ascending: false })
      .limit(80),
    supabase
      .from("kurashift_themes")
      .select(
        "id, title, hypothesis, amount_jpy, funding_path, status, created_at"
      )
      .in("status", ["draft", "consulting", "approved", "executing"])
      .order("created_at", { ascending: false })
      .limit(8),
    supabase
      .from("trade_research")
      .select("id, topic, summary, fetched_at")
      .order("fetched_at", { ascending: false })
      .limit(5),
    supabase
      .from("kurashift_consultations")
      .select("id, title, lane, status, created_at")
      .eq("status", "open")
      .order("created_at", { ascending: false })
      .limit(5),
    supabase
      .from("kurashift_jobs")
      .select("id")
      .eq("job_type", "lifeplan_push_zaim")
      .eq("status", "succeeded")
      .gte("finished_at", `${new Date().getFullYear()}-01-01`)
      .limit(1),
  ]);

  const nameById = new Map((accounts ?? []).map((a) => [a.id, a.name]));
  const latestByAccount = new Map<
    string,
    { as_of: string; value_jpy: number; source: string | null }
  >();
  for (const row of snaps ?? []) {
    if (!latestByAccount.has(row.account_id)) {
      latestByAccount.set(row.account_id, {
        as_of: row.as_of,
        value_jpy: Number(row.value_jpy),
        source: row.source,
      });
    }
  }
  const assetRows = [...latestByAccount.entries()]
    .map(([id, v]) => ({
      id,
      name: nameById.get(id) || id,
      ...v,
    }))
    .sort((a, b) => b.value_jpy - a.value_jpy);
  const total = assetRows.reduce((s, r) => s + r.value_jpy, 0);

  const notice = annualNoticeCopy();
  const showAnnualNotice =
    isAnnualLifeplanWindow() && !(annualDone && annualDone.length > 0);

  const actionable = (themes ?? []).filter((t) =>
    ["draft", "consulting", "approved"].includes(t.status)
  );

  return (
    <Shell active="/" email={user?.email ?? null}>
      <p className="page-kicker">HOME</p>
      <h1>KURASHIFT</h1>
      <p className="sub">
        ①資産運用（把握・テーマ提案／実行）と ②ライフプラン更新・個人申告ネタ。日常のトップは①。
      </p>

      {showAnnualNotice ? (
        <div className="notice">
          <strong>{notice.title}</strong>
          <p style={{ margin: "6px 0 10px" }}>{notice.body}</p>
          <a className="btn primary" href="/lifeplan?mode=annual">
            ライフプラン更新へ
          </a>
        </div>
      ) : null}

      <div className="grid">
        <article className="card">
          <header>
            <span className="lvl">資産合計</span>
            <strong>{fmtYen(total)}</strong>
          </header>
          <p className="meta">{assetRows.length}口座 · 週次スナップ</p>
          <a href="/portfolio">資産の詳細 →</a>
        </article>
        <article className="card">
          <header>
            <span className="lvl">テーマ</span>
            <strong>{themes?.length ?? 0}</strong>
          </header>
          <p className="meta">進行中の投資テーマ</p>
          <a href="/themes">テーマ一覧 →</a>
        </article>
        <article className="card">
          <header>
            <span className="lvl">提案候補</span>
            <strong>{actionable.length}</strong>
          </header>
          <p className="meta">draft / consulting / approved</p>
        </article>
        <article className="card">
          <header>
            <span className="lvl">相談</span>
            <strong>{consults?.length ?? 0}</strong>
          </header>
          <p className="meta">Jarvis オープン相談</p>
          <a href="/consultations">相談記録 →</a>
        </article>
      </div>

      <h2 style={{ marginTop: 28, fontSize: "1.1rem" }}>
        テーマからの投資提案・実行
      </h2>
      <p className="meta" style={{ marginBottom: 12 }}>
        分析→提案→相談→承認→実行。まずは一般的でやりやすいところから。やりづらければ Jarvis
        に相談して見直す。
      </p>
      <EnqueueJobButton
        jobType="theme_propose_from_status"
        title="資産ステータスから提案を生成"
        payload={{ limit: 6 }}
        label="ステータスから提案を生成"
      />

      <div className="card">
        {(themes ?? []).length === 0 ? (
          <p className="meta">
            まだテーマカードがありません。リサーチや資産状況を見ながら Jarvis
            で提案を作り、アプリのテーマへ登録します。
          </p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>状態</th>
                <th>テーマ</th>
                <th>金額</th>
                <th>経路</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {(themes ?? []).map((t) => (
                <tr key={t.id}>
                  <td>{t.status}</td>
                  <td>
                    <strong>{t.title}</strong>
                    <div className="meta">{t.hypothesis}</div>
                  </td>
                  <td>
                    {t.amount_jpy != null ? fmtYen(Number(t.amount_jpy)) : "—"}
                  </td>
                  <td className="meta">{t.funding_path ?? "—"}</td>
                  <td>
                    <EnqueueJobButton
                      jobType="theme_preview"
                      title={`preview ${t.title}`}
                      payload={{ theme_id: t.id }}
                      label="プレビュー"
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p style={{ marginTop: 12 }}>
          <a href="/themes">テーマ運用画面へ →</a>
        </p>
      </div>

      <h2 style={{ marginTop: 28, fontSize: "1.1rem" }}>
        他資産のステータス → 提案の材料
      </h2>
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>口座</th>
              <th>評価</th>
              <th>日付</th>
              <th>ソース</th>
            </tr>
          </thead>
          <tbody>
            {assetRows.length === 0 ? (
              <tr>
                <td colSpan={4} className="meta">
                  スナップショットがありません（週次 portfolio を実行）
                </td>
              </tr>
            ) : (
              assetRows.slice(0, 10).map((r) => (
                <tr key={r.id}>
                  <td>{r.name}</td>
                  <td>{fmtYen(r.value_jpy)}</td>
                  <td className="meta">{r.as_of}</td>
                  <td className="meta">{r.source ?? "—"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
        <p className="meta" style={{ marginTop: 10 }}>
          余力・保険・Bloomo・インデックスの偏りはここを見て Theme
          提案に反映。詳細更新は資産画面／週次ジョブ。
        </p>
        <EnqueueJobButton
          jobType="portfolio_weekly"
          title="資産週次をキュー"
          payload={{}}
          label="資産ステータス更新（週次）"
        />
      </div>

      {(research ?? []).length > 0 ? (
        <>
          <h2 style={{ marginTop: 28, fontSize: "1.1rem" }}>最近のリサーチ</h2>
          <div className="card">
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {(research ?? []).map((r) => (
                <li key={r.id} style={{ marginBottom: 8 }}>
                  <strong>{r.topic || "リサーチ"}</strong>
                  <div className="meta">
                    {(r.summary || "").slice(0, 160)}
                    {(r.summary || "").length > 160 ? "…" : ""}
                  </div>
                </li>
              ))}
            </ul>
            <a href="/research">リサーチ一覧 →</a>
          </div>
        </>
      ) : null}

      <p className="meta" style={{ marginTop: 24 }}>
        ライフプランの年次更新・物件購入時の計画更新は{" "}
        <a href="/lifeplan">ライフプラン</a>
        から。別モードが出たら Jarvis に相談。
      </p>
    </Shell>
  );
}
