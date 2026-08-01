import Link from "next/link";
import Shell from "@/components/Shell";
import DraftWorkbench from "@/components/DraftWorkbench";
import TriageStatusActions from "@/components/TriageStatusActions";
import { gmailSendConfigured } from "@/lib/gmail/sendFromEnv";
import { resolvePartnerToEmail } from "@/lib/partnerContacts";
import { STATUS_LABEL, type TriageStatus } from "@/lib/triageStatus";
import { createClient } from "@/lib/supabase/server";

type LaneView = "unread" | "sent" | "skipped" | "snoozed" | "activity";

const VIEW_LABEL: Record<LaneView, string> = {
  unread: "未読",
  sent: "送信済み",
  skipped: "スキップ",
  snoozed: "後で",
  activity: "活動概要",
};

function parseView(raw: string | undefined): LaneView {
  const v = (raw || "").trim();
  if (v === "sent" || v === "skipped" || v === "snoozed" || v === "activity") {
    return v;
  }
  return "unread";
}

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
};

export default async function TriageLanePage({
  lane,
  title,
  active,
  subtitle,
  searchParams,
}: {
  lane: string;
  title: string;
  active: string;
  subtitle?: string;
  searchParams?: Promise<{ i?: string; view?: string }>;
}) {
  const sp = searchParams ? await searchParams : {};
  const view = parseView(sp.view);
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
    const status = view;
    const { data } = await supabase
      .from("triage_items")
      .select("*")
      .eq("lane", lane)
      .eq("status", status)
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

  const viewHref = (v: LaneView) =>
    v === "unread" ? active : `${active}?view=${v}`;
  const unreadHref = (i: number) =>
    i <= 0 ? active : `${active}?view=unread&i=${i}`;

  const stats: { view: LaneView; count: number }[] = [
    { view: "unread", count: unreadN },
    { view: "sent", count: sentN },
    { view: "skipped", count: skipN },
    { view: "snoozed", count: snoozeN },
    { view: "activity", count: activityN },
  ];

  return (
    <Shell active={active}>
      <h1>{title}</h1>
      {subtitle ? <p className="sub">{subtitle}</p> : null}
      <p className="meta" style={{ marginTop: -8, marginBottom: 12 }}>
        上の数字をタップすると、その一覧だけ表示します（いま: {VIEW_LABEL[view]}
        ）。
      </p>
      <div className="stats" role="tablist" aria-label="表示の切り替え">
        {stats.map((s) => (
          <Link
            key={s.view}
            href={viewHref(s.view)}
            className={`stat stat-link${view === s.view ? " on" : ""}`}
            role="tab"
            aria-selected={view === s.view}
          >
            {VIEW_LABEL[s.view]} <strong>{s.count}</strong>
          </Link>
        ))}
      </div>

      {view === "unread" ? (
        <>
          <h2>未読（1通ずつ）</h2>
          {!focus || !focusTo ? (
            <p className="empty">未読なし</p>
          ) : (
            <>
              <div className="focus-nav">
                <span className="meta">
                  {idx + 1} / {unread.length}
                </span>
                {idx > 0 ? (
                  <Link className="btn" href={unreadHref(idx - 1)}>
                    ← 前
                  </Link>
                ) : (
                  <span className="btn" style={{ opacity: 0.4 }}>
                    ← 前
                  </span>
                )}
                {idx < unread.length - 1 ? (
                  <Link className="btn" href={unreadHref(idx + 1)}>
                    次 →
                  </Link>
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
                    path={active}
                    mode="unread"
                  />
                </header>
                <h3 style={{ fontSize: "1.05rem", margin: "8px 0 6px" }}>
                  {focus.subject}
                </h3>
                {focusTo.to ? <p className="meta">To: {focusTo.to}</p> : null}
                {Boolean(focus.summary) &&
                !isTruncatedBodyPreview(focus.summary, focus.original_body) ? (
                  <p className="sum">
                    <span className="sum-label">要点</span>
                    {focus.summary}
                  </p>
                ) : null}
                <OriginalBodyBlock body={focus.original_body} open />
                <h3 style={{ fontSize: "0.95rem", marginTop: 14 }}>
                  返信下書き
                </h3>
                <DraftWorkbench
                  id={focus.id}
                  path={active}
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
                      path={`${active}?view=${view}`}
                      mode="closed"
                    />
                  </header>
                  <p className="mail-subject" style={{ margin: "6px 0" }}>
                    <Link
                      href={`/mail/${encodeURIComponent(it.id)}`}
                      style={{ color: "var(--accent)", fontWeight: 600 }}
                    >
                      {it.subject || "（件名なし）"}
                    </Link>
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
    </Shell>
  );
}
