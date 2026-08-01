import Shell from "@/components/Shell";
import { createClient } from "@/lib/supabase/server";

export default async function GeneralPage() {
  const supabase = await createClient();
  const { data: pending } = await supabase
    .from("triage_items")
    .select("*")
    .eq("lane", "general")
    .eq("status", "pending")
    .order("received_at", { ascending: true });

  return (
    <Shell active="/general">
      <h1>それ以外（admin Gmail）</h1>
      {!pending?.length ? (
        <p className="empty">pending なし</p>
      ) : (
        pending.map((it) => (
          <article key={it.id} className="card">
            <header>
              <strong>{it.from_email || "—"}</strong>
              <span className="meta">{it.received_at}</span>
            </header>
            <h3 style={{ fontSize: "1.05rem", margin: "8px 0 6px" }}>
              {it.subject}
            </h3>
            <p className="sum">{it.summary}</p>
            {it.draft_text ? (
              <details>
                <summary>下書き</summary>
                <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.85rem" }}>
                  {it.draft_text}
                </pre>
              </details>
            ) : null}
          </article>
        ))
      )}
    </Shell>
  );
}
