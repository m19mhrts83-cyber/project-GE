import Link from "next/link";
import Shell from "@/components/Shell";
import CopyPathButton from "@/components/CopyPathButton";
import OpenchatThreadChart, {
  type OpenchatDayPoint,
} from "@/components/OpenchatThreadChart";
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
  reasons?: string[];
  action?: string;
  needs_bootstrap?: boolean;
};

function parseHealth(raw: unknown): {
  worst?: string;
  summary?: string;
  watch?: Record<string, unknown>;
  batch?: Record<string, unknown>;
  threads_today?: number;
  routes?: RouteEval[];
  daily_series?: OpenchatDayPoint[];
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
    watch: (o.watch as Record<string, unknown>) || {},
    batch: (o.batch as Record<string, unknown>) || {},
    threads_today:
      typeof o.threads_today === "number" ? o.threads_today : undefined,
    routes: Array.isArray(o.routes) ? (o.routes as RouteEval[]) : [],
    daily_series: Array.isArray(o.daily_series)
      ? (o.daily_series as OpenchatDayPoint[])
      : [],
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
    .select("id,title,level,summary,detail,payload,updated_at")
    .in("id", ["openchat_threads", "square_probe"]);

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
        「登録0件で正常終了」などの静かな失敗を監視。情報収集枠のため返信提案はしません。
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
          {health.watch?.last_write_error ? (
            <li className="warn-line">
              書込エラー: {String(health.watch.last_write_error).slice(0, 160)}
            </li>
          ) : null}
        </ul>
      </section>

      <section aria-label="日次グラフ" className="openchat-health-section">
        <h2>直近30日の【スレッド】追記</h2>
        <OpenchatThreadChart points={series} />
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
                    (r.thread_mids_registered || 0) === 0 &&
                    (r.md_replies_14d || 0) > 0;
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
                        {r.action ? (
                          <CopyPathButton
                            path={r.action}
                            label="bootstrap コマンド"
                          />
                        ) : (
                          "—"
                        )}
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
