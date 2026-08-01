import Shell from "@/components/Shell";
import { createClient } from "@/lib/supabase/server";

export default async function OpenchatPage() {
  const supabase = await createClient();
  const { data: activities } = await supabase
    .from("triage_items")
    .select("*")
    .eq("lane", "openchat")
    .eq("kind", "activity")
    .order("received_at", { ascending: false })
    .limit(50);

  return (
    <Shell active="/openchat">
      <h1>神大家オプチャ</h1>
      <p className="sub">情報収集枠。返信提案なし。</p>
      {!activities?.length ? (
        <p className="empty">なし（push 待ち）</p>
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
