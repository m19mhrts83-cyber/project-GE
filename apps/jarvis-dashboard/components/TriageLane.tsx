import Shell from "@/components/Shell";
import TriageDoneToggle from "@/components/TriageDoneToggle";
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

export default async function TriageLanePage({
  lane,
  title,
  active,
  subtitle,
}: {
  lane: string;
  title: string;
  active: string;
  subtitle?: string;
}) {
  const supabase = await createClient();
  const { data: pending } = await supabase
    .from("triage_items")
    .select("*")
    .eq("lane", lane)
    .eq("status", "pending")
    .neq("kind", "activity")
    .order("received_at", { ascending: true });
  const { data: done } = await supabase
    .from("triage_items")
    .select("*")
    .eq("lane", lane)
    .eq("status", "done")
    .neq("kind", "activity")
    .order("updated_at", { ascending: false })
    .limit(30);
  const { data: activities } = await supabase
    .from("triage_items")
    .select("*")
    .eq("lane", lane)
    .eq("kind", "activity")
    .order("received_at", { ascending: false })
    .limit(40);

  return (
    <Shell active={active}>
      <h1>{title}</h1>
      {subtitle ? <p className="sub">{subtitle}</p> : null}
      <div className="stats">
        <div className="stat">
          pending <strong>{pending?.length ?? 0}</strong>
        </div>
        <div className="stat">
          対応済み <strong>{done?.length ?? 0}</strong>
        </div>
        <div className="stat">
          活動概要 <strong>{activities?.length ?? 0}</strong>
        </div>
      </div>
      <h2>要返信・要対応</h2>
      {!pending?.length ? (
        <p className="empty">なし</p>
      ) : (
        pending.map((it) => {
          const showAiSummary =
            Boolean(it.summary) &&
            !isTruncatedBodyPreview(it.summary, it.original_body);
          return (
            <article key={it.id} className="card">
              <header>
                <strong>{it.partner || it.from_email || "—"}</strong>
                <span className="meta">
                  {it.folder} · {it.received_at}
                </span>
                <TriageDoneToggle id={it.id} status={it.status} path={active} />
              </header>
              <h3 style={{ fontSize: "1.05rem", margin: "8px 0 6px" }}>
                {it.subject}
              </h3>
              {showAiSummary ? (
                <p className="sum">
                  <span className="sum-label">要点</span>
                  {it.summary}
                </p>
              ) : null}
              <OriginalBodyBlock body={it.original_body} open />
              {it.draft_text ? (
                <details className="draft-details">
                  <summary>返信下書き</summary>
                  <pre className="draft-body">{it.draft_text}</pre>
                </details>
              ) : null}
            </article>
          );
        })
      )}
      <h2>対応済み</h2>
      {!done?.length ? (
        <p className="empty">なし</p>
      ) : (
        done.map((it) => (
          <article key={it.id} className="card">
            <header>
              <strong>{it.partner || it.from_email || it.subject}</strong>
              <span className="meta">{it.received_at}</span>
              <TriageDoneToggle id={it.id} status={it.status} path={active} />
            </header>
            {it.summary &&
            !isTruncatedBodyPreview(it.summary, it.original_body) ? (
              <p className="sum">{it.summary}</p>
            ) : null}
            <OriginalBodyBlock body={it.original_body} open={false} />
          </article>
        ))
      )}
      <h2>更新概要</h2>
      {!activities?.length ? (
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
    </Shell>
  );
}
