import Link from "next/link";
import Shell from "@/components/Shell";
import CopyPathButton from "@/components/CopyPathButton";
import OpenchatThreadChart, {
  type OpenchatDayPoint,
} from "@/components/OpenchatThreadChart";
import OpenchatHealthRemediation, {
  type Remediation,
} from "@/components/OpenchatHealthRemediation";
import { LEVEL_LABEL, type HomeLevel } from "@/lib/homeLevels";
import { createClient } from "@/lib/supabase/server";

type RouteEval = {
  route_id?: string;
  org_label?: string;
  include_threads?: boolean;
  thread_mids_registered?: number;
  md_threads_14d?: number;
  md_replies_14d?: number;
  md_main_14d?: number;
  appended_threads?: number;
  ok?: number;
  deleted?: number;
  closed?: number;
  last_ok_at?: string | null;
  level?: string;
  symptom?: string;
  reasons?: string[];
  action?: string;
  needs_bootstrap?: boolean;
  cursor_prompt_short?: string;
};

function parseHealth(raw: unknown): {
  worst?: string;
  summary?: string;
  summary_split?: Record<string, unknown>;
  main_freshness?: Record<string, unknown>;
  watch?: Record<string, unknown>;
  batch?: Record<string, unknown>;
  threads_today?: number;
  attention_count?: number;
  routes?: RouteEval[];
  daily_series?: OpenchatDayPoint[];
  remediation?: Remediation | null;
} {
  if (!raw) return {};
  let obj: unknown = raw;
  if (typeof raw === "string") {
    try {
      obj = JSON.parse(raw);
    } catch {
      return {};
    }
  }
  if (!obj || typeof obj !== "object") return {};
  const o = obj as Record<string, unknown>;
  return {
    worst: String(o.worst_level || ""),
    summary: String(o.summary || ""),
    summary_split:
      o.summary_split && typeof o.summary_split === "object"
        ? (o.summary_split as Record<string, unknown>)
        : {},
    main_freshness:
      o.main_freshness && typeof o.main_freshness === "object"
        ? (o.main_freshness as Record<string, unknown>)
        : {},
    watch: (o.watch as Record<string, unknown>) || {},
    batch: (o.batch as Record<string, unknown>) || {},
    threads_today:
      typeof o.threads_today === "number" ? o.threads_today : undefined,
    attention_count:
      typeof o.attention_count === "number" ? o.attention_count : undefined,
    routes: Array.isArray(o.routes) ? (o.routes as RouteEval[]) : [],
    daily_series: Array.isArray(o.daily_series)
      ? (o.daily_series as OpenchatDayPoint[])
      : [],
    remediation:
      o.remediation && typeof o.remediation === "object"
        ? (o.remediation as Remediation)
        : null,
  };
}

function levelBadgeClass(level: string) {
  if (level === "ok") return "lvl-ok";
  if (level === "attention") return "lvl-attention";
  if (level === "warn") return "lvl-warn";
  return "lvl-info";
}

export default async function OpenchatHealthPage() {
  const supabase = await createClient();
  const { data: meta } = await supabase
    .from("sync_meta")
    .select("key,value")
    .eq("key", "openchat_thread_health")
    .maybeSingle();
  const { data: watchRows } = await supabase
    .from("watch_status")
    .select("id,title,level,summary,detail,payload,cursor_prompt,updated_at")
    .in("id", ["openchat_threads", "square_probe"]);
  const { data: comments } = await supabase
    .from("watch_comments")
    .select("id,role,body,created_at")
    .eq("watch_id", "openchat_threads")
    .order("created_at", { ascending: true })
    .limit(40);

  const health = parseHealth(meta?.value);
  const watch = (watchRows || []).find((w) => w.id === "openchat_threads");
  const square = (watchRows || []).find((w) => w.id === "square_probe");
  const payload =
    watch?.payload && typeof watch.payload === "object"
      ? (watch.payload as Record<string, unknown>)
      : {};

  const routes =
    health.routes && health.routes.length
      ? health.routes
      : Array.isArray(payload.routes)
        ? (payload.routes as RouteEval[])
        : [];
  const series = health.daily_series || [];
  const worst =
    health.worst ||
    String(payload.worst_level || watch?.level || "info");
  const summary = health.summary || watch?.summary || "データなし（push 待ち）";
  const summarySplit =
    health.summary_split && Object.keys(health.summary_split).length
      ? health.summary_split
      : (payload.summary_split as Record<string, unknown>) || {};
  const remediation =
    health.remediation ||
    (payload.remediation && typeof payload.remediation === "object"
      ? (payload.remediation as Remediation)
      : null);
  const mainFreshness =
    (health.main_freshness && Object.keys(health.main_freshness).length
      ? health.main_freshness
      : null) ||
    (payload.main_freshness && typeof payload.main_freshness === "object"
      ? (payload.main_freshness as Record<string, unknown>)
      : {});
  const attentionCount =
    health.attention_count ??
    (typeof payload.attention_count === "number"
      ? payload.attention_count
      : 0);
  const writeErr = health.watch?.last_write_error
    ? String(health.watch.last_write_error)
    : null;
  const showRemediation =
    worst !== "ok" ||
    attentionCount > 0 ||
    Boolean(writeErr) ||
    Boolean(remediation?.infra_attention) ||
    Boolean(remediation?.main_stale) ||
    Boolean(mainFreshness?.stale) ||
    Boolean(remediation?.mac_recipe);

  const levelClass =
    worst === "ok" ? "level-info" : `level-${(worst as HomeLevel) || "info"}`;

  const sorted = [...routes].sort((a, b) => {
    const rank: Record<string, number> = {
      attention: 0,
      warn: 1,
      info: 2,
      ok: 3,
    };
    return (rank[a.level || "ok"] ?? 9) - (rank[b.level || "ok"] ?? 9);
  });

  return (
    <Shell active="/openchat/health">
      <p className="crumb">
        <Link href="/openchat">神大家オプチャ</Link> / スレッド健全性
      </p>
      <h1>オプチャ・スレッド取得ヘルス</h1>
      <p className="sub">
        情報収集枠。返信提案なし。予兆を見たら下の解消パネルから Cursor／聞く／Mac
        既知復旧へ。
      </p>

      <section className={`openchat-health ${levelClass}`} aria-label="全体ステータス">
        <div className="openchat-health-head">
          <h2>全体ステータス</h2>
          <Link href="/openchat" className="home-more">
            オプチャ一覧へ →
          </Link>
        </div>
        <p className="openchat-health-status">
          <span className="lvl">
            {worst === "ok"
              ? "健全"
              : LEVEL_LABEL[worst as HomeLevel] || worst}
          </span>{" "}
          <strong>{summary}</strong>
        </p>
        <ul className="openchat-health-meta">
          <li>
            <strong>ルート</strong>:{" "}
            {String(summarySplit.route || `要確認 ${attentionCount}`)}
          </li>
          <li>
            <strong>基盤</strong>:{" "}
            {String(summarySplit.infra || "—")}
            {summarySplit.infra_attention ? " （要確認）" : ""}
          </li>
          <li>
            <strong>メイン鮮度</strong>:{" "}
            {String(
              summarySplit.main ||
                mainFreshness?.summary ||
                "—"
            )}
            {summarySplit.main_stale || mainFreshness?.stale
              ? " （要確認）"
              : ""}
          </li>
          <li>
            常時監視: {String(health.watch?.state || "—")}
            {health.watch?.heartbeat_at
              ? ` · heartbeat ${String(health.watch.heartbeat_at)}`
              : ""}
          </li>
          <li>
            最終バッチ: {String(health.batch?.run_at || "未保存")}
            {health.threads_today != null
              ? ` · 今日【スレッド】${health.threads_today}件`
              : ""}
          </li>
          {square ? (
            <li>
              Square probe: {square.level} — {square.summary}
            </li>
          ) : null}
          {writeErr ? (
            <li className="warn-line">
              書込エラー（基盤）: {writeErr.slice(0, 160)}
            </li>
          ) : null}
        </ul>
      </section>

      <OpenchatHealthRemediation
        show={showRemediation}
        remediation={remediation}
        title={watch?.title || "オプチャ・スレッド取得"}
        summary={summary}
        detail={watch?.detail}
        cursorPrompt={
          remediation?.cursor_prompt || watch?.cursor_prompt || null
        }
        payload={payload}
        comments={(comments || []).map((c) => ({
          id: c.id,
          role: c.role,
          body: c.body,
          created_at: c.created_at,
        }))}
      />

      <section aria-label="日次グラフ" className="openchat-health-section">
        <h2>直近30日の【スレッド】追記</h2>
        <OpenchatThreadChart points={series} />
        <p className="meta">
          棒が細い＋メインはある → 静かな失敗の予兆。メイン鮮度が全ルート0 →
          取込経路（パートナー確認／朝 --with-line）。解消パネルへ。
        </p>
      </section>

      <section aria-label="route別" className="openchat-health-section">
        <h2>ルート別</h2>
        {!sorted.length ? (
          <p className="empty">ルート評価なし（health push 待ち）</p>
        ) : (
          <div className="openchat-route-table-wrap">
            <table className="openchat-route-table">
              <thead>
                <tr>
                  <th>判定</th>
                  <th>グループ</th>
                  <th>登録</th>
                  <th>ok</th>
                  <th>deleted</th>
                  <th>14日スレ</th>
                  <th>14日返信</th>
                  <th>最終ok</th>
                  <th>処置</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((r) => {
                  const lv = r.level || "ok";
                  const silentFail =
                    r.symptom === "silent_fail_empty_mids" ||
                    ((r.thread_mids_registered || 0) === 0 &&
                      ((r.md_replies_14d || 0) > 0 ||
                        (r.md_main_14d || 0) > 0));
                  return (
                    <tr
                      key={r.route_id}
                      className={silentFail ? "row-attention" : undefined}
                    >
                      <td>
                        <span className={`badge ${levelBadgeClass(lv)}`}>
                          {lv === "ok"
                            ? "OK"
                            : LEVEL_LABEL[lv as HomeLevel] || lv}
                        </span>
                      </td>
                      <td>
                        <strong>{r.org_label || r.route_id}</strong>
                        {silentFail ? (
                          <div className="warn-line">
                            未登録スレあり — bootstrap 要
                          </div>
                        ) : null}
                        {(r.reasons || []).length ? (
                          <div className="meta">
                            {(r.reasons || []).slice(0, 2).join(" / ")}
                          </div>
                        ) : null}
                      </td>
                      <td>{r.thread_mids_registered ?? "—"}</td>
                      <td>{r.ok ?? "—"}</td>
                      <td>{r.deleted ?? "—"}</td>
                      <td>{r.md_threads_14d ?? "—"}</td>
                      <td>{r.md_replies_14d ?? "—"}</td>
                      <td className="meta">
                        {r.last_ok_at
                          ? String(r.last_ok_at).slice(0, 16)
                          : "—"}
                      </td>
                      <td>
                        <div className="openchat-remediation-actions">
                          {r.action ? (
                            <CopyPathButton
                              path={r.action}
                              label="bootstrap コマンド"
                            />
                          ) : null}
                          {r.cursor_prompt_short ? (
                            <CopyPathButton
                              path={r.cursor_prompt_short}
                              label="短プロンプト"
                            />
                          ) : null}
                          {!r.action && !r.cursor_prompt_short ? "—" : null}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </Shell>
  );
}
