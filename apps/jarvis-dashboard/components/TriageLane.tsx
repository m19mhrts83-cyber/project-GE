import Shell from "@/components/Shell";
import TriageDoneToggle from "@/components/TriageDoneToggle";
import { createClient } from "@/lib/supabase/server";

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
        pending.map((it) => (
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
            <p className="sum">{it.summary}</p>
            {it.draft_text ? (
              <details>
                <summary>下書き</summary>
                <pre
                  style={{
                    whiteSpace: "pre-wrap",
                    fontSize: "0.85rem",
                    background: "#fafaf9",
                    padding: 12,
                    borderRadius: 8,
                  }}
                >
                  {it.draft_text}
                </pre>
              </details>
            ) : null}
            {it.original_body ? (
              <details>
                <summary>本文</summary>
                <pre
                  style={{
                    whiteSpace: "pre-wrap",
                    fontSize: "0.8rem",
                    background: "#fafaf9",
                    padding: 12,
                    borderRadius: 8,
                    maxHeight: 320,
                    overflow: "auto",
                  }}
                >
                  {it.original_body}
                </pre>
              </details>
            ) : null}
          </article>
        ))
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
            <p className="sum">{it.summary}</p>
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
          </article>
        ))
      )}
    </Shell>
  );
}
