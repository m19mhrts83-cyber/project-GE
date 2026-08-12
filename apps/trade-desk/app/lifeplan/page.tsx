import Shell from "@/components/Shell";
import EnqueueJobButton from "@/components/EnqueueJobButton";
import { createClient } from "@/lib/supabase/server";
import { fmtYen } from "@/lib/format";
import {
  annualNoticeCopy,
  isAnnualLifeplanWindow,
  parseLifeplanMode,
  type LifeplanMode,
} from "@/lib/lifeplanNotices";

export const dynamic = "force-dynamic";

type Metrics = {
  kind?: string;
  alpha_pct?: number | null;
  beta_pct?: number | null;
  gamma_pct?: number | null;
  alpha_target_pct?: number | null;
  beta_target_pct?: number | null;
  gamma_target_pct?: number | null;
  income_household_jpy?: number | null;
  expense_alpha_jpy?: number | null;
  expense_beta_jpy?: number | null;
  expense_gamma_jpy?: number | null;
  expense_delta_re_jpy?: number | null;
  targets?: {
    alpha_save_pct?: number;
    beta_living_pct?: number;
    gamma_self_pct?: number;
  };
  source?: string;
};

const STEPS = [
  {
    n: 1,
    job: "lifeplan_ingest_actuals",
    title: "年度実績を取り込む",
    desc: "Zaim 年度サマリーから αβγ を集計（δ不動産は分母外）。表1補正の材料にする。",
  },
  {
    n: 2,
    job: "lifeplan_revise_budget",
    title: "実績を見て予算を補正する",
    desc: "αβγ 20/60/20 とのギャップを出し、Numbers でその年の予算を作る。",
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
    desc: "Numbers→CSV まで自動。Zaim 本番反映は別途確認付き（confirm_apply）。",
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

function AbgBar({
  label,
  pct,
  target,
}: {
  label: string;
  pct: number | null | undefined;
  target: number;
}) {
  const v = pct ?? 0;
  const width = Math.max(0, Math.min(100, v));
  const delta = pct == null ? null : Math.round((pct - target) * 10) / 10;
  return (
    <div style={{ marginBottom: 10 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          fontSize: 13,
        }}
      >
        <strong>
          {label} {pct == null ? "—" : `${pct}%`}
        </strong>
        <span className="meta">
          目標 {target}%
          {delta == null ? "" : `（${delta > 0 ? "+" : ""}${delta}pt）`}
        </span>
      </div>
      <div
        style={{
          height: 8,
          background: "rgba(0,0,0,0.08)",
          borderRadius: 4,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${width}%`,
            height: "100%",
            background: "var(--accent, #2a6f6a)",
          }}
        />
      </div>
    </div>
  );
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
      .limit(20),
    supabase
      .from("kurashift_jobs")
      .select("id, job_type, status, title, created_at, finished_at, error_text")
      .like("job_type", "lifeplan_%")
      .order("created_at", { ascending: false })
      .limit(15),
  ]);

  const actualsSnap = (snaps ?? []).find((s) => {
    const m = s.metrics as Metrics | null;
    return m?.kind === "actuals";
  });
  const planSnap = (snaps ?? []).find((s) => {
    const m = s.metrics as Metrics | null;
    return m?.kind === "plan" || !m?.kind;
  });
  const actuals = (actualsSnap?.metrics || null) as Metrics | null;
  const planM = (planSnap?.metrics || null) as Metrics | null;

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

  const targets = actuals?.targets || {
    alpha_save_pct: 20,
    beta_living_pct: 60,
    gamma_self_pct: 20,
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

      {actuals ? (
        <div className="card" style={{ marginBottom: 16 }}>
          <header>
            <span className="lvl">αβγ 実績</span>
            <strong>
              {actualsSnap?.fiscal_year ?? notice.actualsYear}年（世帯収入比）
            </strong>
          </header>
          <p className="meta">
            世帯収入{" "}
            {actuals.income_household_jpy != null
              ? fmtYen(actuals.income_household_jpy)
              : "—"}
            {" · "}δ不動産支出は分母外
            {actuals.expense_delta_re_jpy != null
              ? `（${fmtYen(actuals.expense_delta_re_jpy)}）`
              : ""}
          </p>
          <AbgBar
            label="α 貯蓄・投資"
            pct={actuals.alpha_pct}
            target={targets.alpha_save_pct ?? 20}
          />
          <AbgBar
            label="β 生活"
            pct={actuals.beta_pct}
            target={targets.beta_living_pct ?? 60}
          />
          <AbgBar
            label="γ 自己・教育"
            pct={actuals.gamma_pct}
            target={targets.gamma_self_pct ?? 20}
          />
          <p className="meta">
            α{" "}
            {actuals.expense_alpha_jpy != null
              ? fmtYen(actuals.expense_alpha_jpy)
              : "—"}
            {" / "}β{" "}
            {actuals.expense_beta_jpy != null
              ? fmtYen(actuals.expense_beta_jpy)
              : "—"}
            {" / "}γ{" "}
            {actuals.expense_gamma_jpy != null
              ? fmtYen(actuals.expense_gamma_jpy)
              : "—"}
          </p>
        </div>
      ) : (
        <div className="card" style={{ marginBottom: 16 }}>
          <p className="meta" style={{ margin: 0 }}>
            まだ実績スナップがありません。Step1「年度実績を取り込む」を実行してください。
          </p>
        </div>
      )}

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
                  payload={
                    s.job === "lifeplan_push_zaim"
                      ? { ...fiscalPayload, confirm_apply: false }
                      : fiscalPayload
                  }
                  label="実行キューへ"
                />
                {s.job === "lifeplan_push_zaim" ? (
                  <EnqueueJobButton
                    jobType="lifeplan_push_zaim"
                    title={`${intro.heading}: Zaim本番反映`}
                    payload={{ ...fiscalPayload, confirm_apply: true }}
                    label="Zaim本番反映（要確認）"
                  />
                ) : null}
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
          <span className="lvl">比較</span>
          <strong>実績 vs 直近計画スナップ</strong>
        </header>
        <table>
          <thead>
            <tr>
              <th>項目</th>
              <th>実績</th>
              <th>計画スナップ</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>α %</td>
              <td>{actuals?.alpha_pct ?? "—"}</td>
              <td>{planM?.alpha_target_pct ?? planM?.alpha_pct ?? "—"}</td>
            </tr>
            <tr>
              <td>β %</td>
              <td>{actuals?.beta_pct ?? "—"}</td>
              <td>{planM?.beta_target_pct ?? planM?.beta_pct ?? "—"}</td>
            </tr>
            <tr>
              <td>γ %</td>
              <td>{actuals?.gamma_pct ?? "—"}</td>
              <td>{planM?.gamma_target_pct ?? planM?.gamma_pct ?? "—"}</td>
            </tr>
            <tr>
              <td>ラベル</td>
              <td className="meta">{actualsSnap?.label ?? "—"}</td>
              <td className="meta">{planSnap?.label ?? "—"}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="card" style={{ marginTop: 20 }}>
        <header>
          <span className="lvl">スナップショット</span>
          <strong>計画の時点一覧</strong>
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
              <th>種別</th>
              <th>ラベル</th>
              <th>年度</th>
              <th>日付</th>
              <th>メモ</th>
            </tr>
          </thead>
          <tbody>
            {(snaps ?? []).length === 0 ? (
              <tr>
                <td colSpan={5} className="meta">
                  まだありません
                </td>
              </tr>
            ) : (
              (snaps ?? []).map((r) => {
                const m = r.metrics as Metrics | null;
                return (
                  <tr key={r.id}>
                    <td>{m?.kind ?? "—"}</td>
                    <td>{r.label}</td>
                    <td>{r.fiscal_year ?? "—"}</td>
                    <td>{r.snapshot_at}</td>
                    <td className="meta">{r.notes ?? "—"}</td>
                  </tr>
                );
              })
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
