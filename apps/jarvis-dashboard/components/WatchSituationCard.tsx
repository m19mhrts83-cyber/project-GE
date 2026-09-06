import Link from "next/link";
import MarkdownLite from "@/components/MarkdownLite";
import OpsFixAckButton from "@/components/OpsFixAckButton";
import StatusToggle from "@/components/StatusToggle";
import WatchAckButton from "@/components/WatchAckButton";
import CardDebitAckButton from "@/components/CardDebitAckButton";
import CardDebitSettleButton from "@/components/CardDebitSettleButton";
import WatchCommentThread, {
  type WatchCommentRow,
} from "@/components/WatchCommentThread";
import { LEVEL_LABEL, type HomeLevel } from "@/lib/homeLevels";
import { isOpsEphemeralId } from "@/lib/opsWatch";
import { isMarkdownWatchId, readWatchMdItems } from "@/lib/watchMdItems";

type ActionItem = {
  date?: string;
  shop?: string;
  amount?: number;
  proposal?: string;
  line?: string;
  kind?: string;
};

function yen(n: number | undefined) {
  if (n == null || Number.isNaN(n)) return "—";
  return `¥${Math.round(n).toLocaleString("ja-JP")}`;
}

function isYmdDate(raw: string | undefined): boolean {
  return Boolean(raw && /^\d{4}-\d{2}-\d{2}$/.test(raw));
}

export type WatchSituationCardProps = {
  id: string;
  title: string;
  level: string;
  summary: string | null;
  detail: string | null;
  source: string | null;
  status: string;
  cursorPrompt: string | null;
  payload: Record<string, unknown>;
  actions: ActionItem[];
  comments: WatchCommentRow[];
  neverArchive: boolean;
  showOpsAck: boolean;
};

/** 状況ウォッチ1件。初期は折りたたみ、summary クリックで展開 */
export default function WatchSituationCard(props: WatchSituationCardProps) {
  const {
    id,
    title,
    level: rawLevel,
    summary,
    detail,
    source,
    status,
    cursorPrompt,
    payload,
    actions,
    comments,
    neverArchive,
    showOpsAck,
  } = props;

  const level = (
    ["attention", "warn", "info", "ok"].includes(rawLevel) ? rawLevel : "info"
  ) as HomeLevel | "ok";
  const label =
    level === "ok" ? "OK" : LEVEL_LABEL[level as HomeLevel] || rawLevel;
  const mdItems = readWatchMdItems(payload);
  const renderMdDetail = isMarkdownWatchId(id) || mdItems.length > 0;

  return (
    <details
      id={`watch-${id}`}
      data-watch-id={id}
      className={`card watch-fold level-${rawLevel}`}
    >
      <summary className="watch-fold-summary">
        <header className="watch-fold-head">
          <span className="lvl">{label}</span>
          <strong>{title}</strong>
          {source ? <span className="meta">{source}</span> : null}
          <span className="watch-fold-chevron" aria-hidden>
            展開
          </span>
        </header>
        {summary ? <p className="sum watch-fold-sum">{summary}</p> : null}
      </summary>

      <div className="watch-fold-body">
        <div className="watch-fold-toolbar">
          {isOpsEphemeralId(String(id)) ? (
            <span className="meta" style={{ fontSize: "0.78rem" }}>
              {id === "ops_fix_notice" ? "確認で消す" : "解決で消える"}
            </span>
          ) : (
            <StatusToggle
              table="watch_status"
              id={id}
              status={status}
              path="/situation"
              neverArchive={neverArchive}
            />
          )}
        </div>

        {showOpsAck ? <OpsFixAckButton /> : null}
        <WatchAckButton
          watchId={String(id)}
          level={rawLevel}
          summary={summary}
          payload={payload}
        />
        {id === "card_debit_watch" ? (
          <p className="meta" style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            <CardDebitSettleButton
              dueDate={
                typeof payload.due_date === "string"
                  ? payload.due_date
                  : payload.olive_infinite &&
                      typeof payload.olive_infinite === "object" &&
                      typeof (payload.olive_infinite as { due_date?: string })
                        .due_date === "string"
                    ? (payload.olive_infinite as { due_date: string }).due_date
                    : ""
              }
            />
            <CardDebitAckButton
              dueDate={
                typeof payload.due_date === "string"
                  ? payload.due_date
                  : payload.olive_infinite &&
                      typeof payload.olive_infinite === "object" &&
                      typeof (payload.olive_infinite as { due_date?: string })
                        .due_date === "string"
                    ? (payload.olive_infinite as { due_date: string }).due_date
                    : ""
              }
            />
            {typeof payload.action_url === "string" ? (
              <a href={payload.action_url} target="_blank" rel="noreferrer">
                KURASHIFT で寄せ計画 →
              </a>
            ) : null}
          </p>
        ) : null}
        {id === "etc_mileage" ? (
          <p className="meta">
            <Link href="/etc">ETCページ（還元サマリ・申請案内）→</Link>
          </p>
        ) : null}
        {id === "vpoint" ? (
          <p className="meta">
            <Link href="/vpoint">Vポイントページ（付与サマリ・考察）→</Link>
          </p>
        ) : null}
        {id === "rent_step" ? (
          <p className="meta">
            <Link href="/rent-step">家賃ステップ（+4,000・変動）→</Link>
          </p>
        ) : null}
        {id === "zaim_quality" ? (
          <p className="meta">
            <Link href="/zaim">Zaim Watch（年間収支・直し確認）→</Link>
          </p>
        ) : null}
        {id === "card_debit_watch" ? (
          <p className="meta" style={{ marginTop: 8 }}>
            <strong>処置は KURASHIFT で</strong>
            {" · "}
            <a
              href={
                typeof payload.action_url === "string"
                  ? payload.action_url
                  : typeof payload.href === "string" &&
                      String(payload.href).startsWith("http")
                    ? String(payload.href)
                    : "https://jarvis-trade-desk.vercel.app/money-ops"
              }
              target="_blank"
              rel="noopener noreferrer"
            >
              資金移動オペ（寄せ計画）を開く ↗
            </a>
          </p>
        ) : null}
        {id === "openchat_threads" ? (
          <p className="meta">
            <Link href="/openchat">神大家オプチャ →</Link>
          </p>
        ) : null}

        {id === "cursor_worker_queue" ? (
          <div
            className="cursor-worker-queue-box"
            style={{
              marginTop: 10,
              padding: 12,
              background: "var(--bg-subtle, #f8fafc)",
              borderRadius: 8,
              border: "1px solid var(--border, #e2e8f0)",
            }}
          >
            <div
              style={{
                display: "flex",
                gap: 8,
                alignItems: "center",
                marginBottom: 10,
                flexWrap: "wrap",
              }}
            >
              <span
                style={{
                  padding: "3px 8px",
                  borderRadius: 4,
                  fontSize: 11,
                  fontWeight: 700,
                  background:
                    ((payload.counts as Record<string, number>)?.queued || 0) > 0
                      ? "#3b82f6"
                      : "#94a3b8",
                  color: "#fff",
                }}
              >
                待機: {((payload.counts as Record<string, number>)?.queued) || 0}件
              </span>
              <span
                style={{
                  padding: "3px 8px",
                  borderRadius: 4,
                  fontSize: 11,
                  fontWeight: 700,
                  background:
                    ((payload.counts as Record<string, number>)?.running || 0) > 0
                      ? "#f59e0b"
                      : "#94a3b8",
                  color: "#fff",
                }}
              >
                処理中: {((payload.counts as Record<string, number>)?.running) || 0}件
              </span>
              <span
                style={{
                  padding: "3px 8px",
                  borderRadius: 4,
                  fontSize: 11,
                  fontWeight: 700,
                  background:
                    ((payload.counts as Record<string, number>)?.error || 0) > 0
                      ? "#ef4444"
                      : "#10b981",
                  color: "#fff",
                }}
              >
                エラー: {((payload.counts as Record<string, number>)?.error) || 0}件
              </span>
              <span
                style={{
                  padding: "3px 8px",
                  borderRadius: 4,
                  fontSize: 11,
                  fontWeight: 600,
                  background: "#64748b",
                  color: "#fff",
                }}
              >
                直近完了: {((payload.counts as Record<string, number>)?.done_recent) || 0}件
              </span>
            </div>

            {/* 待機中の相談リスト */}
            {Array.isArray(payload.queued_items) && payload.queued_items.length > 0 ? (
              <div style={{ marginTop: 8 }}>
                <strong style={{ fontSize: "0.85rem", color: "#1e3a8a" }}>
                  ⏳ 待機中の相談（Macワーカーが順次処理）:
                </strong>
                <ul style={{ margin: "4px 0 0 16px", fontSize: "0.85rem" }}>
                  {(
                    payload.queued_items as Array<{
                      id: string;
                      title: string;
                      kind: string;
                      requested_at?: string;
                      href: string;
                    }>
                  ).map((item) => (
                    <li key={item.id} style={{ marginTop: 3 }}>
                      <Link
                        href={item.href}
                        style={{ textDecoration: "underline", fontWeight: 600, color: "#2563eb" }}
                      >
                        {item.title}
                      </Link>
                      <span className="meta" style={{ marginLeft: 6 }}>
                        ({item.kind} / {item.requested_at ? item.requested_at.slice(11, 16) : "—"})
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {/* 処理中の相談リスト */}
            {Array.isArray(payload.running_items) && payload.running_items.length > 0 ? (
              <div style={{ marginTop: 8 }}>
                <strong style={{ fontSize: "0.85rem", color: "#b45309" }}>
                  ⚡️ 処理中（回答生成中）:
                </strong>
                <ul style={{ margin: "4px 0 0 16px", fontSize: "0.85rem" }}>
                  {(
                    payload.running_items as Array<{
                      id: string;
                      title: string;
                      kind: string;
                      started_at?: string;
                      href: string;
                    }>
                  ).map((item) => (
                    <li key={item.id} style={{ marginTop: 3 }}>
                      <Link
                        href={item.href}
                        style={{ textDecoration: "underline", fontWeight: 600, color: "#d97706" }}
                      >
                        {item.title}
                      </Link>
                      <span className="meta" style={{ marginLeft: 6 }}>
                        ({item.started_at ? item.started_at.slice(11, 16) : "—"} 開始)
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {/* エラーリスト */}
            {Array.isArray(payload.error_items) && payload.error_items.length > 0 ? (
              <div
                style={{
                  marginTop: 8,
                  padding: 8,
                  background: "#fee2e2",
                  borderRadius: 6,
                  border: "1px solid #f87171",
                }}
              >
                <strong style={{ fontSize: "0.85rem", color: "#b91c1c" }}>
                  ⚠️ エラー発生（自動リトライ対象）:
                </strong>
                <ul style={{ margin: "4px 0 0 16px", fontSize: "0.85rem", color: "#7f1d1d" }}>
                  {(
                    payload.error_items as Array<{
                      id: string;
                      title: string;
                      error?: string;
                      href: string;
                    }>
                  ).map((item) => (
                    <li key={item.id} style={{ marginTop: 3 }}>
                      <Link
                        href={item.href}
                        style={{ textDecoration: "underline", fontWeight: 600, color: "#dc2626" }}
                      >
                        {item.title}
                      </Link>
                      : {item.error || "詳細不明"}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {/* 直近完了リスト */}
            {Array.isArray(payload.recent_done) && payload.recent_done.length > 0 ? (
              <div style={{ marginTop: 8 }}>
                <strong style={{ fontSize: "0.85rem", color: "#065f46" }}>
                  ✅ 直近完了した相談（回答確認はこちら）:
                </strong>
                <ul style={{ margin: "4px 0 0 16px", fontSize: "0.85rem" }}>
                  {(
                    payload.recent_done as Array<{
                      id: string;
                      title: string;
                      finished_at?: string;
                      href: string;
                    }>
                  ).map((item) => (
                    <li key={item.id} style={{ marginTop: 3 }}>
                      <Link
                        href={item.href}
                        style={{ textDecoration: "underline", fontWeight: 600, color: "#059669" }}
                      >
                        {item.title}
                      </Link>
                      <span className="meta" style={{ marginLeft: 6 }}>
                        ({item.finished_at ? item.finished_at.slice(11, 16) : "—"} 完了)
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            <p className="meta" style={{ marginTop: 10, fontSize: "0.78rem" }}>
              ワーカー稼働: Mac launchd（45秒間隔） · 最終更新:{" "}
              {typeof payload.last_heartbeat === "string"
                ? payload.last_heartbeat.slice(11, 19)
                : "—"}
            </p>
          </div>
        ) : null}

        {actions.length > 0 ? (
          <div className="watch-actions">
            <p className="watch-actions-title">要対応（具体）</p>
            <ul>
              {actions.map((a, idx) => {
                const showDate = isYmdDate(a.date);
                const showYen = a.amount != null && !Number.isNaN(a.amount);
                const stacked = !showDate || !showYen;
                return (
                  <li
                    key={`${a.date}-${a.shop}-${a.amount}-${idx}`}
                    className={stacked ? "watch-action-stack" : undefined}
                  >
                    {showDate ? (
                      <span className="watch-action-date">{a.date}</span>
                    ) : null}
                    <span className="watch-action-shop">{a.shop || "—"}</span>
                    {showYen ? (
                      <span className="watch-action-yen">{yen(a.amount)}</span>
                    ) : null}
                    <span className="watch-action-proposal">
                      {a.proposal || a.line || "—"}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        ) : mdItems.length > 0 ? (
          <div className="watch-inbox-md">
            {mdItems.map((it) => (
              <article key={it.name || it.title} className="watch-inbox-md-item">
                <header className="watch-md-head">
                  {it.name ? <span className="meta">{it.name}</span> : null}
                  {it.action ? (
                    <span className="watch-md-pill">{it.action}</span>
                  ) : null}
                  {it.priority ? (
                    <span className="watch-md-pill">{it.priority}</span>
                  ) : null}
                </header>
                {it.bodyMd ? (
                  <MarkdownLite source={it.bodyMd} />
                ) : it.title ? (
                  <p>{it.title}</p>
                ) : null}
              </article>
            ))}
          </div>
        ) : detail && renderMdDetail ? (
          <MarkdownLite source={detail} />
        ) : detail ? (
          <pre className="watch-detail">{detail}</pre>
        ) : null}
        {actions.length > 0 &&
        detail &&
        !String(detail).includes("要対応:") ? (
          renderMdDetail ? (
            <MarkdownLite source={detail} />
          ) : (
            <pre className="watch-detail">{detail}</pre>
          )
        ) : null}
        {cursorPrompt ? (
          <details className="watch-prompt-details">
            <summary>Cursor用メモ</summary>
            <pre className="watch-detail">{cursorPrompt}</pre>
          </details>
        ) : null}
        <WatchCommentThread
          watchId={id}
          title={title}
          summary={summary}
          detail={detail}
          cursorPrompt={cursorPrompt}
          payload={payload}
          comments={comments}
          path="/situation"
        />
      </div>
    </details>
  );
}
