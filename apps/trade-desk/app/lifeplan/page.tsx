import Shell from "@/components/Shell";
import EnqueueJobButton from "@/components/EnqueueJobButton";
import { createClient } from "@/lib/supabase/server";
import {
  annualNoticeCopy,
  isAnnualLifeplanWindow,
  parseLifeplanMode,
  type LifeplanMode,
} from "@/lib/lifeplanNotices";

export const dynamic = "force-dynamic";

const STEPS = [
  {
    n: 1,
    job: "lifeplan_ingest_actuals",
    title: "年度実績を取り込む",
    desc: "財務から対象年度の実績を整理し、表1／表2／CF に載せる準備。",
  },
  {
    n: 2,
    job: "lifeplan_revise_budget",
    title: "実績を見て予算を補正する",
    desc: "αβγ 20/60/20 と統制（○△×）を見ながらその年の予算を作る。",
  },
  {
    n: 3,
    job: "lifeplan_update_century",
    title: "100年ライフプランを更新する",
    desc: "予算ベースで CF をチューニングし、固める。相談は Jarvis。",
  },
  {
    n: 4,
    job: "lifeplan_push_zaim",
    title: "固めた予算を財務へ反映する",
    desc: "月別計画 → Zaim 予算（既存 zaim_budget_sync）。Numbers 正本は 260621。",
  },
];

function modeIntro(mode: LifeplanMode, actualsYear: number, planYear: number) {
  if (mode === "annual") {
    return {
      heading: "年次更新モード",
      blurb: `${actualsYear}年実績の確定を受けて、${planYear}年以降のライフプランと予算を更新します（年1〜3回のうちの定例）。`,
    };
  }
  if (mode === "re_purchase") {
    return {
      heading: "不動産購入モード",
      blurb:
        "物件購入タイミングの計画更新。ローン・家賃・修繕・δ不動産CFを反映し、スナップショットを残してからルーティンを回します。",
    };
  }
  return {
    heading: "ライフプラン",
    blurb:
      "日常のトップではなく、振り返り用レーン。定例は年末〜年始、イベントは物件購入時。他のモードが出たら Jarvis に相談。",
  };
}

export default async function LifeplanPage({
  searchParams,
}: {
  searchParams: Promise<{ mode?: string }>;
}) {
  const sp = await searchParams;
  const mode = parseLifeplanMode(sp.mode);
  const notice = annualNoticeCopy();
  const intro = modeIntro(mode, notice.actualsYear, notice.planYear);

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const [{ data: snaps }, { data: jobs }] = await Promise.all([
    supabase
      .from("kurashift_plan_snapshots")
      .select("id, label, fiscal_year, snapshot_at, metrics, notes")
      .order("snapshot_at", { ascending: false })
      .limit(12),
    supabase
      .from("kurashift_jobs")
      .select("id, job_type, status, title, created_at, finished_at, error_text")
      .like("job_type", "lifeplan_%")
      .order("created_at", { ascending: false })
      .limit(15),
  ]);

  const fiscalPayload =
    mode === "re_purchase"
      ? {
          fiscal_year: notice.planYear,
          trigger: "re_purchase",
        }
      : {
          fiscal_year: notice.actualsYear,
          trigger: mode === "annual" ? "annual" : "manual",
          plan_year: notice.planYear,
        };

  return (
    <Shell active="/lifeplan" email={user?.email ?? null}>
      <h1>{intro.heading}</h1>
      <p className="sub">{intro.blurb}</p>

      {isAnnualLifeplanWindow() && mode !== "annual" ? (
        <div className="notice">
          <strong>{notice.title}</strong>
          <p style={{ margin: "6px 0 10px" }}>{notice.body}</p>
          <a className="btn primary" href="/lifeplan?mode=annual">
            年次更新を始める
          </a>
        </div>
      ) : null}

      <div className="grid" style={{ marginBottom: 8 }}>
        <article className="card">
          <header>
            <span className="lvl">トリガー</span>
            <strong>年末〜年始</strong>
          </header>
          <p className="meta">
            12月終了後にお知らせ。年間実績確定 → 以降の LP／予算更新。
          </p>
          <a className="btn" href="/lifeplan?mode=annual">
            年次更新モード
          </a>
        </article>
        <article className="card">
          <header>
            <span className="lvl">トリガー</span>
            <strong>不動産購入</strong>
          </header>
          <p className="meta">
            購入時に計画を更新。19不動産・CF・δを見直し、スナップショットを残す。
          </p>
          <a className="btn" href="/lifeplan?mode=re_purchase">
            物件購入で計画更新
          </a>
        </article>
        <article className="card">
          <header>
            <span className="lvl">その他</span>
            <strong>Jarvis 相談</strong>
          </header>
          <p className="meta">
            別モードが必要になったらチャットで相談。結果は相談レーンへ。
          </p>
          <a href="/consultations">相談記録 →</a>
        </article>
      </div>

      {mode === "re_purchase" ? (
        <div className="card" style={{ marginBottom: 16 }}>
          <header>
            <span className="lvl">物件購入</span>
            <strong>まず計画スナップショット</strong>
          </header>
          <p className="meta">
            更新前の計画を残してから、下記ルーティンで CF／予算を直します。
          </p>
          <EnqueueJobButton
            jobType="lifeplan_snapshot"
            title="購入前スナップショット"
            payload={{
              fiscal_year: notice.planYear,
              trigger: "re_purchase",
              label: `re_purchase_before_${notice.planYear}`,
            }}
            label="購入前スナップを保存"
          />
        </div>
      ) : null}

      {(mode === "annual" || mode === "re_purchase") && (
        <>
          <h2 style={{ fontSize: "1.05rem" }}>ルーティン（4段階）</h2>
          <div className="grid">
            {STEPS.map((s) => (
              <article className="card" key={s.job}>
                <header>
                  <span className="lvl">Step {s.n}</span>
                  <strong>{s.title}</strong>
                </header>
                <p className="meta">{s.desc}</p>
                <EnqueueJobButton
                  jobType={s.job}
                  title={`${intro.heading}: ${s.title}`}
                  payload={fiscalPayload}
                  label="実行キューへ"
                />
              </article>
            ))}
          </div>
        </>
      )}

      {mode === "default" ? (
        <div className="card" style={{ marginTop: 8 }}>
          <p className="meta" style={{ margin: 0 }}>
            上のトリガーからモードを選ぶと、4段階ルーティンが表示されます。トップ画面の主戦場はテーマ投資です。
          </p>
        </div>
      ) : null}

      <div className="card" style={{ marginTop: 20 }}>
        <header>
          <span className="lvl">スナップショット</span>
          <strong>計画の時点比較</strong>
        </header>
        <EnqueueJobButton
          jobType="lifeplan_snapshot"
          title="今の計画を保存"
          payload={{
            fiscal_year: notice.planYear,
            trigger: mode,
          }}
        />
        <table>
          <thead>
            <tr>
              <th>ラベル</th>
              <th>年度</th>
              <th>日付</th>
              <th>メモ</th>
            </tr>
          </thead>
          <tbody>
            {(snaps ?? []).length === 0 ? (
              <tr>
                <td colSpan={4} className="meta">
                  まだありません
                </td>
              </tr>
            ) : (
              (snaps ?? []).map((r) => (
                <tr key={r.id}>
                  <td>{r.label}</td>
                  <td>{r.fiscal_year ?? "—"}</td>
                  <td>{r.snapshot_at}</td>
                  <td className="meta">{r.notes ?? "—"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="card" style={{ marginTop: 20 }}>
        <header>
          <span className="lvl">最近のジョブ</span>
          <strong>lifeplan_*</strong>
        </header>
        <table>
          <thead>
            <tr>
              <th>状態</th>
              <th>種別</th>
              <th>タイトル</th>
              <th>作成</th>
            </tr>
          </thead>
          <tbody>
            {(jobs ?? []).length === 0 ? (
              <tr>
                <td colSpan={4} className="meta">
                  ジョブなし
                </td>
              </tr>
            ) : (
              (jobs ?? []).map((j) => (
                <tr key={j.id}>
                  <td>{j.status}</td>
                  <td>{j.job_type}</td>
                  <td>{j.title}</td>
                  <td className="meta">{j.created_at?.slice(0, 19)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}
