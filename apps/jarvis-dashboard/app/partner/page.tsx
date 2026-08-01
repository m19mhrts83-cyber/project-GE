import Shell from "@/components/Shell";
import { createClient } from "@/lib/supabase/server";

async function LanePage({
  lane,
  title,
  active,
}: {
  lane: string;
  title: string;
  active: string;
}) {
  const supabase = await createClient();
  const { data: pending } = await supabase
    .from("triage_items")
    .select("*")
    .eq("lane", lane)
    .eq("status", "pending")
    .neq("kind", "activity")
    .order("received_at", { ascending: true });
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
      <div className="stats">
        <div className="stat">
          pending <strong>{pending?.length ?? 0}</strong>
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

export default async function PartnerPage() {
  return await LanePage({
    lane: "partner",
    title: "パートナー",
    active: "/partner",
  });
}
