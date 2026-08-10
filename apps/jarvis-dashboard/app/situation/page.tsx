import Link from "next/link";
import Shell from "@/components/Shell";
import OpsFixAckButton from "@/components/OpsFixAckButton";
import StatusToggle from "@/components/StatusToggle";
import WatchAckButton from "@/components/WatchAckButton";
import WatchCommentThread, {
  type WatchCommentRow,
} from "@/components/WatchCommentThread";
import WatchHashFocus from "@/components/WatchHashFocus";
import { LEVEL_LABEL, HomeLevel, watchSortKey } from "@/lib/homeLevels";
import {
  isOpsEphemeralId,
  opsWatchVisibleOnSituation,
} from "@/lib/opsWatch";
import { createClient } from "@/lib/supabase/server";

type ActionItem = {
  date?: string;
  shop?: string;
  amount?: number;
  proposal?: string;
  line?: string;
  kind?: string;
};

function readActions(payload: unknown): ActionItem[] {
  if (!payload || typeof payload !== "object") return [];
  const actions = (payload as { actions?: unknown }).actions;
  if (!Array.isArray(actions)) return [];
  return actions.filter((a) => a && typeof a === "object") as ActionItem[];
}

function yen(n: number | undefined) {
  if (n == null || Number.isNaN(n)) return "—";
  return `¥${Math.round(n).toLocaleString("ja-JP")}`;
}

/** Zaim 用の YYYY-MM-DD。それ以外（アクションID等）は日付列に出さない */
function isYmdDate(raw: string | undefined): boolean {
  return Boolean(raw && /^\d{4}-\d{2}-\d{2}$/.test(raw));
}

export default async function SituationPage() {
  const supabase = await createClient();
  const { data: items } = await supabase
    .from("watch_status")
    .select("*")
    .order("updated_at", { ascending: false });

  const active = (items || []).filter((i) => {
    if (i.status !== "active") return false;
    // Vercel/GHA/直したよは問題・お知らせがあるときだけ一覧表示
    if (isOpsEphemeralId(String(i.id))) {
      return opsWatchVisibleOnSituation(i);
    }
    return true;
  });
  const archivedCount = (items || []).filter((i) => i.status === "archived").length;
  active.sort((a, b) => {
    const pa =
      a.payload && typeof a.payload === "object"
        ? (a.payload as Record<string, unknown>)
        : {};
    const pb =
      b.payload && typeof b.payload === "object"
        ? (b.payload as Record<string, unknown>)
        : {};
    const pinA =
      (pa.pin_top === true || a.id === "cursor_pro_plus_downgrade") &&
      a.level !== "ok";
    const pinB =
      (pb.pin_top === true || b.id === "cursor_pro_plus_downgrade") &&
      b.level !== "ok";
    if (pinA !== pinB) return pinA ? -1 : 1;
    return watchSortKey(a.level) - watchSortKey(b.level);
  });

  const ids = active.map((i) => i.id);
  const commentsByWatch = new Map<string, WatchCommentRow[]>();
  if (ids.length) {
    const { data: comments } = await supabase
      .from("watch_comments")
      .select("id,watch_id,role,body,created_at")
      .in("watch_id", ids)
      .order("created_at", { ascending: true });
    for (const c of comments || []) {
      const list = commentsByWatch.get(c.watch_id) || [];
      list.push({
        id: c.id,
        role: c.role,
        body: c.body,
        created_at: c.created_at,
      });
      commentsByWatch.set(c.watch_id, list);
    }
  }

  return (
    <Shell active="/situation">
      <WatchHashFocus />
      <h1>状況ウォッチ</h1>
      <p className="sub">
        気にしている項目（3段階: 要確認／注意／参考）。要対応は日付・店・金額まで表示。
        Vercel／GHA 失敗と「直したよ」は問題・お知らせがあるときだけ表示し、確認または解決で消えます（アーカイブに溜めません）。
        各項目で Jarvis に詳しく聞けます。復元は{" "}
        <Link href="/archive" style={{ color: "var(--accent)", fontWeight: 600 }}>
          アーカイブ
        </Link>
        から。
      </p>
      <div className="stats">
        <div className="stat">
          アクティブ <strong>{active.length}</strong>
        </div>
        <div className="stat">
          アーカイブ{" "}
          <strong>
            <Link href="/archive" style={{ color: "inherit" }}>
              {archivedCount}
            </Link>
          </strong>
        </div>
      </div>
      <h2>アクティブ</h2>
      {active.length === 0 ? (
        <p className="empty">まだ push されていません</p>
      ) : (
        active.map((it) => {
          const level = (
            ["attention", "warn", "info", "ok"].includes(it.level)
              ? it.level
              : "info"
          ) as HomeLevel | "ok";
          const label =
            level === "ok" ? "OK" : LEVEL_LABEL[level as HomeLevel] || it.level;
          const actions = readActions(it.payload);
          const pl =
            it.payload && typeof it.payload === "object"
              ? (it.payload as Record<string, unknown>)
              : {};
          const neverArchive = Boolean(
            pl.never_archive || isOpsEphemeralId(String(it.id)),
          );
          const showOpsAck =
            it.id === "ops_fix_notice" && pl.show_banner === true;
          return (
            <article
              key={it.id}
              id={`watch-${it.id}`}
              data-watch-id={it.id}
              className={`card level-${it.level}`}
            >
              <header>
                <span className="lvl">{label}</span>
                <strong>{it.title}</strong>
                <span className="meta">{it.source}</span>
                {isOpsEphemeralId(String(it.id)) ? (
                  <span
                    className="meta"
                    style={{ marginLeft: "auto", fontSize: "0.78rem" }}
                  >
                    {it.id === "ops_fix_notice"
                      ? "確認で消す"
                      : "解決で消える"}
                  </span>
                ) : (
                  <StatusToggle
                    table="watch_status"
                    id={it.id}
                    status={it.status}
                    path="/situation"
                    neverArchive={neverArchive}
                  />
                )}
              </header>
              <p className="sum">{it.summary}</p>
              {showOpsAck ? <OpsFixAckButton /> : null}
              <WatchAckButton
                watchId={String(it.id)}
                level={it.level}
                summary={it.summary}
                payload={pl}
              />
              {it.id === "etc_mileage" ? (
                <p className="meta">
                  <Link href="/etc">ETCページ（還元サマリ・申請案内）→</Link>
                </p>
              ) : null}
              {it.id === "vpoint" ? (
                <p className="meta">
                  <Link href="/vpoint">Vポイントページ（付与サマリ・考察）→</Link>
                </p>
              ) : null}
              {it.id === "rent_step" ? (
                <p className="meta">
                  <Link href="/rent-step">家賃ステップ（+4,000・変動）→</Link>
                </p>
              ) : null}
              {it.id === "zaim_quality" ? (
                <p className="meta">
                  <Link href="/zaim">Zaim Watch（年間収支・直し確認）→</Link>
                </p>
              ) : null}
              {actions.length > 0 ? (
                <div className="watch-actions">
                  <p className="watch-actions-title">要対応（具体）</p>
                  <ul>
                    {actions.map((a, idx) => {
                      const showDate = isYmdDate(a.date);
                      const showYen =
                        a.amount != null && !Number.isNaN(a.amount);
                      const stacked = !showDate || !showYen;
                      return (
                        <li
                          key={`${a.date}-${a.shop}-${a.amount}-${idx}`}
                          className={stacked ? "watch-action-stack" : undefined}
                        >
                          {showDate ? (
                            <span className="watch-action-date">{a.date}</span>
                          ) : null}
                          <span className="watch-action-shop">
                            {a.shop || "—"}
                          </span>
                          {showYen ? (
                            <span className="watch-action-yen">
                              {yen(a.amount)}
                            </span>
                          ) : null}
                          <span className="watch-action-proposal">
                            {a.proposal || a.line || "—"}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ) : it.detail ? (
                <pre className="watch-detail">{it.detail}</pre>
              ) : null}
              {actions.length > 0 && it.detail && !String(it.detail).includes("要対応:") ? (
                <pre className="watch-detail">{it.detail}</pre>
              ) : null}
              {it.cursor_prompt ? (
                <details className="watch-prompt-details">
                  <summary>Cursor用メモ</summary>
                  <pre className="watch-detail">{it.cursor_prompt}</pre>
                </details>
              ) : null}
              <WatchCommentThread
                watchId={it.id}
                title={it.title}
                summary={it.summary}
                detail={it.detail}
                cursorPrompt={it.cursor_prompt}
                payload={
                  it.payload && typeof it.payload === "object"
                    ? (it.payload as Record<string, unknown>)
                    : null
                }
                comments={commentsByWatch.get(it.id) || []}
                path="/situation"
              />
            </article>
          );
        })
      )}
      <p className="sub" style={{ marginTop: 24 }}>
        <Link href="/archive" className="btn">
          アーカイブを見る →
        </Link>
      </p>
    </Shell>
  );
}
