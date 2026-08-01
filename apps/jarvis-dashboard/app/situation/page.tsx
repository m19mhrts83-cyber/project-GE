import Link from "next/link";
import Shell from "@/components/Shell";
import StatusToggle from "@/components/StatusToggle";
import { LEVEL_LABEL, HomeLevel, watchSortKey } from "@/lib/homeLevels";
import { createClient } from "@/lib/supabase/server";

export default async function SituationPage() {
  const supabase = await createClient();
  const { data: items } = await supabase
    .from("watch_status")
    .select("*")
    .order("updated_at", { ascending: false });

  const active = (items || []).filter((i) => i.status === "active");
  const archivedCount = (items || []).filter((i) => i.status === "archived").length;
  active.sort((a, b) => watchSortKey(a.level) - watchSortKey(b.level));

  return (
    <Shell active="/situation">
      <h1>状況ウォッチ</h1>
      <p className="sub">
        気にしている項目（3段階: 要確認／注意／参考）。不要になったらアーカイブ。
        復元は{" "}
        <Link href="/archive" style={{ color: "var(--accent)", fontWeight: 600 }}>
          アーカイブ
        </Link>
        メニューから。
      </p>
      <div className="stats">
        <div className="stat">
          アクティブ <strong>{active.length}</strong>
        </div>
        <div className="stat">
          アーカイブ{" "}
          <strong>
            <Link href="/archive" style={{ color: "inherit" }}>
              {archivedCount}
            </Link>
          </strong>
        </div>
      </div>
      <h2>アクティブ</h2>
      {active.length === 0 ? (
        <p className="empty">まだ push されていません</p>
      ) : (
        active.map((it) => {
          const level = (
            ["attention", "warn", "info", "ok"].includes(it.level)
              ? it.level
              : "info"
          ) as HomeLevel | "ok";
          const label =
            level === "ok" ? "OK" : LEVEL_LABEL[level as HomeLevel] || it.level;
          return (
            <article key={it.id} className={`card level-${it.level}`}>
              <header>
                <span className="lvl">{label}</span>
                <strong>{it.title}</strong>
                <span className="meta">{it.source}</span>
                <StatusToggle
                  table="watch_status"
                  id={it.id}
                  status={it.status}
                  path="/situation"
                />
              </header>
              <p className="sum">{it.summary}</p>
              {it.detail ? <p className="meta">{it.detail}</p> : null}
              {it.cursor_prompt ? (
                <pre
                  style={{
                    whiteSpace: "pre-wrap",
                    fontSize: "0.8rem",
                    background: "#fafaf9",
                    padding: 10,
                    borderRadius: 8,
                    border: "1px solid var(--line)",
                    color: "var(--ink)",
                  }}
                >
                  {it.cursor_prompt}
                </pre>
              ) : null}
            </article>
          );
        })
      )}
      <p className="sub" style={{ marginTop: 24 }}>
        <Link href="/archive" className="btn">
          アーカイブを見る →
        </Link>
      </p>
    </Shell>
  );
}
