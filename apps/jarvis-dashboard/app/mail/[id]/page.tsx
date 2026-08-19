import Link from "next/link";
import { notFound } from "next/navigation";
import Shell from "@/components/Shell";
import DraftWorkbench from "@/components/DraftWorkbench";
import FolderLinks from "@/components/FolderLinks";
import MailBodyView from "@/components/MailBodyView";
import MailTaskHandoff from "@/components/MailTaskHandoff";
import TriageStatusActions from "@/components/TriageStatusActions";
import { ensureMailJa } from "@/app/actions/triage";
import { gmailSendConfigured } from "@/lib/gmail/sendFromEnv";
import { fetchMailVisuals } from "@/lib/gmail/fetchMessageParts";
import {
  getFolderLinksMany,
  partnerFolderKey,
} from "@/lib/folderLinks";
import { resolvePartnerToEmail } from "@/lib/partnerContacts";
import {
  LEVEL_LABEL,
  laneHref,
  laneLabel,
  mailPriorityToLevel,
} from "@/lib/homeLevels";
import { STATUS_LABEL, type TriageStatus } from "@/lib/triageStatus";
import { createClient } from "@/lib/supabase/server";

/** Cursor Cloud Agent 見直しの待ち時間用 */
export const maxDuration = 120;

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

  const ja = await ensureMailJa(it.id);
  const payload =
    it.payload && typeof it.payload === "object"
      ? (it.payload as Record<string, unknown>)
      : {};
  const bodyJa =
    ja.bodyJa || (typeof payload.body_ja === "string" ? payload.body_ja : "");
  const subjectJa =
    ja.subjectJa ||
    (typeof payload.subject_ja === "string" ? payload.subject_ja : "");
  const draftJa =
    ja.draftJa || (typeof payload.draft_ja === "string" ? payload.draft_ja : "");

  const visuals = await fetchMailVisuals({
    triageId: it.id,
    gmailMessageId: it.gmail_message_id,
    account: it.account,
  });

  const level = mailPriorityToLevel(it.priority);
  const body = (it.original_body || "").trim();
  const lanePath = laneHref(it.lane);
  const path = `/mail/${it.id}`;
  const gmailReady = gmailSendConfigured();
  const st = it.status as TriageStatus;
  const resolved = resolvePartnerToEmail({
    fromEmail: it.from_email,
    partner: it.partner,
    folder: it.folder,
    payload,
  });
  const folderLinks = getFolderLinksMany([
    partnerFolderKey(it.folder, it.partner),
  ]);

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
        <FolderLinks links={folderLinks} />
        <h1 style={{ fontSize: "1.25rem", margin: "10px 0 8px" }}>
          {subjectJa || it.subject || "（件名なし）"}
        </h1>
        {subjectJa && it.subject && subjectJa !== it.subject ? (
          <p className="meta">原文件名: {it.subject}</p>
        ) : null}
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
        <MailBodyView
          triageId={it.id}
          body={body}
          bodyJa={bodyJa}
          html={visuals.html}
          images={visuals.images}
          files={visuals.files}
          visualsError={visuals.error}
        />
        <h2 style={{ fontSize: "1rem", marginTop: 16 }}>返信下書き</h2>
        <DraftWorkbench
          id={it.id}
          path={path}
          subject={it.subject}
          toEmail={it.from_email}
          partner={it.partner}
          folder={it.folder}
          lane={it.lane}
          draftText={it.draft_text}
          draftJa={draftJa}
          payload={it.payload}
          status={it.status}
          gmailReady={gmailReady}
          resolvedTo={resolved.to}
          toSource={resolved.source}
        />
        <MailTaskHandoff id={it.id} path={path} payload={it.payload} />
      </article>
    </Shell>
  );
}
