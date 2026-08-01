import Link from "next/link";
import { notFound } from "next/navigation";
import Shell from "@/components/Shell";
import DraftWorkbench from "@/components/DraftWorkbench";
import TriageStatusActions from "@/components/TriageStatusActions";
import { gmailSendConfigured } from "@/lib/gmail/sendFromEnv";
import {
  LEVEL_LABEL,
  laneHref,
  laneLabel,
  mailPriorityToLevel,
} from "@/lib/homeLevels";
import { STATUS_LABEL, type TriageStatus } from "@/lib/triageStatus";
import { createClient } from "@/lib/supabase/server";

export default async function MailDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const supabase = await createClient();
  const { data: it } = await supabase
    .from("triage_items")
    .select("*")
    .eq("id", id)
    .maybeSingle();

  if (!it) notFound();

  const level = mailPriorityToLevel(it.priority);
  const body = (it.original_body || "").trim();
  const lanePath = laneHref(it.lane);
  const path = `/mail/${it.id}`;
  const gmailReady = gmailSendConfigured();
  const st = it.status as TriageStatus;

  return (
    <Shell active="/">
      <p className="home-crumb">
        <Link href="/">← ホーム</Link>
        {" · "}
        <Link href={lanePath}>{laneLabel(it.lane)}</Link>
      </p>
      <article className={`card level-${level}`}>
        <header>
          <span className="lvl">{LEVEL_LABEL[level]}</span>
          <span className={`status-badge status-${st}`}>
            {STATUS_LABEL[st] || st}
          </span>
          <strong>{it.partner || it.from_email || "—"}</strong>
          <span className="meta">
            {laneLabel(it.lane)}
            {it.folder ? ` · ${it.folder}` : ""}
            {it.received_at ? ` · ${it.received_at}` : ""}
          </span>
          <TriageStatusActions id={it.id} status={it.status} path={path} />
        </header>
        <h1 style={{ fontSize: "1.25rem", margin: "10px 0 8px" }}>
          {it.subject || "（件名なし）"}
        </h1>
        {it.from_email ? (
          <p className="meta">From: {it.from_email}</p>
        ) : null}
        {it.summary ? (
          <p className="sum">
            <span className="sum-label">要点</span>
            {it.summary}
          </p>
        ) : null}
        <h2 style={{ fontSize: "1rem", marginTop: 16 }}>本文</h2>
        {body ? (
          <pre className="orig-body">{body}</pre>
        ) : (
          <p className="empty" style={{ padding: "8px 0" }}>
            （元メール本文は未保存。次回の Mac 夜間バッチ／GHA 取得後に表示されます）
          </p>
        )}
        <h2 style={{ fontSize: "1rem", marginTop: 16 }}>返信下書き</h2>
        <DraftWorkbench
          id={it.id}
          path={path}
          subject={it.subject}
          toEmail={it.from_email}
          draftText={it.draft_text}
          payload={it.payload}
          status={it.status}
          gmailReady={gmailReady}
        />
      </article>
    </Shell>
  );
}
