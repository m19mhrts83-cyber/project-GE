import Link from "next/link";
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
        ) : detail ? (
          <pre className="watch-detail">{detail}</pre>
        ) : null}
        {actions.length > 0 &&
        detail &&
        !String(detail).includes("要対応:") ? (
          <pre className="watch-detail">{detail}</pre>
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
