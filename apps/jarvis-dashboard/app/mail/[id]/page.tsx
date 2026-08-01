import Link from "next/link";
import { notFound } from "next/navigation";
import Shell from "@/components/Shell";
import TriageDoneToggle from "@/components/TriageDoneToggle";
import {
  LEVEL_LABEL,
  laneHref,
  laneLabel,
  mailPriorityToLevel,
} from "@/lib/homeLevels";
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
          <strong>{it.partner || it.from_email || "—"}</strong>
          <span className="meta">
            {laneLabel(it.lane)}
            {it.folder ? ` · ${it.folder}` : ""}
            {it.received_at ? ` · ${it.received_at}` : ""}
          </span>
          <TriageDoneToggle id={it.id} status={it.status} path={`/mail/${it.id}`} />
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
        {it.draft_text ? (
          <details className="draft-details" open>
            <summary>返信下書き</summary>
            <pre className="draft-body">{it.draft_text}</pre>
          </details>
        ) : null}
      </article>
    </Shell>
  );
}
