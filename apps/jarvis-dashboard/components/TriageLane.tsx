import Shell from "@/components/Shell";
import BulkSkipNonPartnerButton from "@/components/BulkSkipNonPartnerButton";
import DraftWorkbench from "@/components/DraftWorkbench";
import TriageStatusActions from "@/components/TriageStatusActions";
import PartnerKeyboardNav from "@/components/PartnerKeyboardNav";
import LaneViewTabs from "@/components/LaneViewTabs";
import { gmailSendConfigured } from "@/lib/gmail/sendFromEnv";
import { fetchMailVisuals } from "@/lib/gmail/fetchMessageParts";
import MailBodyView from "@/components/MailBodyView";
import { LEVEL_LABEL, mailPriorityToLevel } from "@/lib/homeLevels";
import {
  VIEW_LABEL,
  laneViewHref,
  type LaneView,
} from "@/lib/laneView";
import { resolvePartnerToEmail } from "@/lib/partnerContacts";
import { STATUS_LABEL, type TriageStatus } from "@/lib/triageStatus";
import { createClient } from "@/lib/supabase/server";

/** summary が原文の先頭切り出しだけなら、カード上では出さない（全文側に寄せる） */
function isTruncatedBodyPreview(
  summary: string | null | undefined,
  original: string | null | undefined,
): boolean {
  const s = (summary || "").replace(/\s+/g, " ").trim();
  const o = (original || "").replace(/\s+/g, " ").trim();
  if (!s || !o) return false;
  if (s.length >= o.length) return s === o || o.startsWith(s.slice(0, 120));
  const head = o.slice(0, Math.min(s.length + 20, o.length));
  return head.startsWith(s.slice(0, Math.min(100, s.length)));
}

function OriginalBodyBlock({
  body,
  open = true,
}: {
  body: string | null | undefined;
  open?: boolean;
}) {
  const text = (body || "").trim();
  if (!text) {
    return (
      <p className="empty" style={{ marginTop: 8 }}>
        （元メール本文は未保存。次回の Mac 夜間バッチ／GHA 取得後に表示されます）
      </p>
    );
  }
  return (
    <details open={open} className="orig-details">
      <summary>元メール全文</summary>
      <pre className="orig-body">{text}</pre>
    </details>
  );
}

type TriageRow = {
  id: string;
  status: string;
  partner: string | null;
  folder: string | null;
  from_email: string | null;
  subject: string | null;
  summary: string | null;
  original_body: string | null;
  received_at: string | null;
  draft_text: string | null;
  payload: unknown;
  channel: string | null;
  priority?: string | null;
  gmail_message_id?: string | null;
  account?: string | null;
};

export default async function TriageLanePage({
  lane,
  title,
  active,
  subtitle,
  view: viewProp,
  searchParams,
}: {
  lane: string;
  title: string;
  active: string;
  subtitle?: string;
  /** パス /partner/sent から渡す。未指定時は unread */
  view?: LaneView;
  searchParams?: Promise<{ i?: string; view?: string }>;
}) {
  const sp = searchParams ? await searchParams : {};
  const view: LaneView = viewProp || "unread";
  const supabase = await createClient();

  const countFor = async (opts: {
    status?: string;
    kindActivity?: boolean;
  }) => {
    let q = supabase
      .from("triage_items")
      .select("id", { count: "exact", head: true })
      .eq("lane", lane);
    if (opts.kindActivity) {
      q = q.eq("kind", "activity");
    } else {
      q = q.neq("kind", "activity");
      if (opts.status) q = q.eq("status", opts.status);
    }
    const { count } = await q;
    return count ?? 0;
  };

  const [unreadN, sentN, skipN, snoozeN, activityN] = await Promise.all([
    countFor({ status: "pending" }),
    countFor({ status: "sent" }),
    countFor({ status: "skipped" }),
    countFor({ status: "snoozed" }),
    countFor({ kindActivity: true }),
  ]);

  let unread: TriageRow[] = [];
  let closedList: TriageRow[] = [];
  let activities: TriageRow[] = [];

  if (view === "unread") {
    const { data: pending } = await supabase
      .from("triage_items")
      .select("*")
      .eq("lane", lane)
      .eq("status", "pending")
      .neq("kind", "activity")
      .order("received_at", { ascending: true });
    unread = (pending || []) as TriageRow[];
  } else if (view === "activity") {
    const { data } = await supabase
      .from("triage_items")
      .select("*")
      .eq("lane", lane)
      .eq("kind", "activity")
      .order("received_at", { ascending: false })
      .limit(80);
    activities = (data || []) as TriageRow[];
  } else {
    const { data } = await supabase
      .from("triage_items")
      .select("*")
      .eq("lane", lane)
      .eq("status", view)
      .neq("kind", "activity")
      .order("updated_at", { ascending: false })
      .limit(80);
    closedList = (data || []) as TriageRow[];
  }

  const idxRaw = Number.parseInt(String(sp.i || "0"), 10);
  const idx =
    unread.length === 0
      ? 0
      : Math.min(
          Math.max(Number.isFinite(idxRaw) ? idxRaw : 0, 0),
          unread.length - 1,
        );
  const focus = unread[idx];
  const gmailReady = gmailSendConfigured();
  const focusPayload =
    focus?.payload && typeof focus.payload === "object"
      ? (focus.payload as Record<string, unknown>)
      : {};
  const focusVisuals = focus
    ? await fetchMailVisuals({
        triageId: focus.id,
        gmailMessageId: focus.gmail_message_id,
        account: focus.account,
      })
    : { html: null, images: [], error: undefined };
  const focusTo = focus
    ? resolvePartnerToEmail({
        fromEmail: focus.from_email,
        partner: focus.partner,
        folder: focus.folder,
        payload:
          focus.payload && typeof focus.payload === "object"
            ? (focus.payload as Record<string, unknown>)
            : null,
      })
    : null;

  const unreadHref = (i: number) => laneViewHref(active, "unread", i);
  const viewPath = laneViewHref(active, view);
  const skimUnread = lane !== "partner";

  const stats = [
    { view: "unread" as const, count: unreadN },
    { view: "sent" as const, count: sentN },
    { view: "skipped" as const, count: skipN },
    { view: "snoozed" as const, count: snoozeN },
    { view: "activity" as const, count: activityN },
  ];

  return (
    <Shell active={active}>
      <h1>{title}</h1>
      {subtitle ? (
        <p className="sub">{subtitle}</p>
      ) : skimUnread ? (
        <p className="sub">
          ざざっと見て必要なものだけ開く。終わったら一括スキップ。
        </p>
      ) : null}
      <LaneViewTabs basePath={active} current={view} stats={stats} />

      <div key={view} id="lane-view-panel">
        {view === "unread" && skimUnread ? (
          <>
            <div className="other-mail-toolbar" style={{ marginBottom: 12 }}>
              <h2 style={{ margin: 0, fontSize: "1.05rem" }}>
                未読（一覧）
              </h2>
              <BulkSkipNonPartnerButton
                path={viewPath}
                pendingCount={unread.length}
              />
            </div>
            {!unread.length ? (
              <p className="empty">未読なし</p>
            ) : (
              <ul className="mail-skim">
                {unread.map((it) => {
                  const level = mailPriorityToLevel(it.priority);
                  const who = it.partner || it.from_email || "—";
                  const oneLine = (it.summary || "")
                    .replace(/\s+/g, " ")
                    .trim();
                  return (
                    <li key={it.id}>
                      <a
                        href={`/mail/${encodeURIComponent(it.id)}`}
                        className={`mail-row level-${level}`}
                      >
                        <span className="lvl">{LEVEL_LABEL[level]}</span>
                        <span className="mail-row-main">
                          <span className="mail-row-top">
                            <strong>{who}</strong>
                            <span className="meta">
                              {it.received_at || ""}
                            </span>
                          </span>
                          <span className="mail-subject">
                            {it.subject || "（件名なし）"}
                          </span>
                          {oneLine &&
                          !isTruncatedBodyPreview(
                            it.summary,
                            it.original_body,
                          ) ? (
                            <span className="mail-preview">{oneLine}</span>
                          ) : null}
                        </span>
                        <span className="mail-chevron" aria-hidden>
                          ›
                        </span>
                      </a>
                    </li>
                  );
                })}
              </ul>
            )}
          </>
        ) : null}

        {view === "unread" && !skimUnread ? (
          <>
            <h2>未読（1通ずつ）</h2>
            <PartnerKeyboardNav
              idx={idx}
              total={unread.length}
              focusId={focus?.id ?? null}
              path={viewPath}
              prevHref={idx > 0 ? unreadHref(idx - 1) : null}
              nextHref={
                idx < unread.length - 1 ? unreadHref(idx + 1) : null
              }
            />
            {!focus || !focusTo ? (
              <p className="empty">未読なし</p>
            ) : (
              <>
                <div className="focus-nav">
                  <span className="meta">
                    {idx + 1} / {unread.length}
                  </span>
                  {idx > 0 ? (
                    <a className="btn" href={unreadHref(idx - 1)}>
                      ← 前
                    </a>
                  ) : (
                    <span className="btn" style={{ opacity: 0.4 }}>
                      ← 前
                    </span>
                  )}
                  {idx < unread.length - 1 ? (
                    <a className="btn" href={unreadHref(idx + 1)}>
                      次 →
                    </a>
                  ) : (
                    <span className="btn" style={{ opacity: 0.4 }}>
                      次 →
                    </span>
                  )}
                </div>
                <article className="card focus-card">
                  <header>
                    <strong>{focus.partner || focus.from_email || "—"}</strong>
                    <span className="meta">
                      {focus.folder} · {focus.received_at}
                    </span>
                    <TriageStatusActions
                      id={focus.id}
                      status={focus.status}
                      path={viewPath}
                      mode="unread"
                      snoozeUntil={
                        focus.payload &&
                        typeof focus.payload === "object" &&
                        typeof (focus.payload as { snooze_until?: unknown })
                          .snooze_until === "string"
                          ? ((focus.payload as { snooze_until: string })
                              .snooze_until)
                          : null
                      }
                    />
                  </header>
                  <h3 style={{ fontSize: "1.05rem", margin: "8px 0 6px" }}>
                    <a
                      href={`/mail/${encodeURIComponent(focus.id)}`}
                      style={{ color: "var(--accent)", fontWeight: 600 }}
                    >
                      {focus.subject || "（件名なし）"}
                    </a>
                  </h3>
                  {focusTo.to ? (
                    <p className="meta">To: {focusTo.to}</p>
                  ) : null}
                  {Boolean(focus.summary) &&
                  !isTruncatedBodyPreview(
                    focus.summary,
                    focus.original_body,
                  ) ? (
                    <p className="sum">
                      <span className="sum-label">要点</span>
                      {focus.summary}
                    </p>
                  ) : null}
                  <MailBodyView
                    triageId={focus.id}
                    body={focus.original_body}
                    bodyJa={
                      typeof focusPayload.body_ja === "string"
                        ? focusPayload.body_ja
                        : ""
                    }
                    html={focusVisuals.html}
                    images={focusVisuals.images}
                    visualsError={focusVisuals.error}
                    open
                  />
                  <h3 style={{ fontSize: "0.95rem", marginTop: 14 }}>
                    返信下書き
                  </h3>
                  <DraftWorkbench
                    id={focus.id}
                    path={viewPath}
                    subject={focus.subject}
                    toEmail={focus.from_email}
                    partner={focus.partner}
                    folder={focus.folder}
                    lane={lane}
                    draftText={focus.draft_text}
                    payload={focus.payload}
                    status={focus.status}
                    gmailReady={gmailReady}
                    resolvedTo={focusTo.to}
                    toSource={focusTo.source}
                  />
                </article>
              </>
            )}
          </>
        ) : null}

        {view === "sent" || view === "skipped" || view === "snoozed" ? (
          <>
            <h2>{VIEW_LABEL[view]}</h2>
            {!closedList.length ? (
              <p className="empty">なし</p>
            ) : (
              closedList.map((it) => {
                const st = it.status as TriageStatus;
                const appended = Boolean(
                  it.payload &&
                    typeof it.payload === "object" &&
                    (it.payload as { yoritoori_appended?: boolean })
                      .yoritoori_appended,
                );
                return (
                  <article key={it.id} className="card">
                    <header>
                      <span className={`status-badge status-${st}`}>
                        {STATUS_LABEL[st] || st}
                      </span>
                      <strong>
                        {it.partner || it.from_email || it.subject}
                      </strong>
                      <span className="meta">{it.received_at}</span>
                      <TriageStatusActions
                        id={it.id}
                        status={it.status}
                        path={viewPath}
                        mode="closed"
                        snoozeUntil={
                          it.payload &&
                          typeof it.payload === "object" &&
                          typeof (it.payload as { snooze_until?: unknown })
                            .snooze_until === "string"
                            ? ((it.payload as { snooze_until: string })
                                .snooze_until)
                            : null
                        }
                      />
                    </header>
                    <p className="mail-subject" style={{ margin: "6px 0" }}>
                      <a
                        href={`/mail/${encodeURIComponent(it.id)}`}
                        style={{ color: "var(--accent)", fontWeight: 600 }}
                      >
                        {it.subject || "（件名なし）"}
                      </a>
                    </p>
                    {st === "sent" ? (
                      <p className="meta">
                        {appended
                          ? "送信済み・やり取り反映済"
                          : "送信済み（やり取り追記は Mac 同期後）"}
                      </p>
                    ) : null}
                    {it.summary &&
                    !isTruncatedBodyPreview(it.summary, it.original_body) ? (
                      <p className="sum">{it.summary}</p>
                    ) : null}
                    <OriginalBodyBlock body={it.original_body} open={false} />
                  </article>
                );
              })
            )}
          </>
        ) : null}

        {view === "activity" ? (
          <>
            <h2>活動概要</h2>
            {!activities.length ? (
              <p className="empty">なし</p>
            ) : (
              activities.map((it) => (
                <article key={it.id} className="card">
                  <header>
                    <span className="lvl">{it.channel || "更新"}</span>
                    <strong>{it.partner}</strong>
                    <span className="meta">{it.received_at}</span>
                  </header>
                  <p className="sum">{it.summary || it.subject}</p>
                  {it.original_body ? (
                    <OriginalBodyBlock body={it.original_body} open={false} />
                  ) : null}
                </article>
              ))
            )}
          </>
        ) : null}
      </div>
    </Shell>
  );
}
