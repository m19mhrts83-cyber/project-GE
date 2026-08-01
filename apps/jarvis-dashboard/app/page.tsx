import Shell from "@/components/Shell";
import { createClient } from "@/lib/supabase/server";

export default async function HomePage() {
  const supabase = await createClient();
  const { count: pending } = await supabase
    .from("triage_items")
    .select("*", { count: "exact", head: true })
    .eq("status", "pending")
    .neq("kind", "activity");
  const { count: watchWarn } = await supabase
    .from("watch_status")
    .select("*", { count: "exact", head: true })
    .eq("status", "active")
    .in("level", ["attention", "warn"]);
  const { data: meta } = await supabase.from("sync_meta").select("key,value");

  const metaMap = Object.fromEntries((meta || []).map((m) => [m.key, m.value]));

  return (
    <Shell active="/">
      <h1>Jarvis ダッシュボード</h1>
      <p className="sub">
        メールを起点に、状況ウォッチなどをサイドバーから。iPhone からも閲覧可（要ログイン）。
      </p>
      <div className="stats">
        <div className="stat">
          メール pending <strong>{pending ?? 0}</strong>
        </div>
        <div className="stat">
          状況要注意 <strong>{watchWarn ?? 0}</strong>
        </div>
        <div className="stat">
          triage sync {metaMap.triage_pushed_at ?? "未push"}
        </div>
        <div className="stat">
          取得経路 <strong>{metaMap.triage_source ?? "—"}</strong>
        </div>
        <div className="stat">
          Mac取得 {metaMap.mac_triage_pushed_at ?? "—"}
        </div>
        <div className="stat">
          GHA取得 {metaMap.gha_triage_pushed_at ?? "—"}
        </div>
        <div className="stat">
          watch sync {metaMap.watch_pushed_at ?? "未push"}
        </div>
        <div className="stat">
          GHA watch {metaMap.gha_watch_pushed_at ?? "—"}
        </div>
        <div className="stat">
          GHA心拍 {metaMap.gha_heartbeat_at ?? "—"}
        </div>
        <div className="stat">
          cards sync {metaMap.cards_pushed_at ?? "—"}
        </div>
      </div>
      <p className="empty">
        左のサイドバーからレーンを開いてください。収集は Mac 夜間バッチまたは GHA
        （Gmail general）→ Supabase。下書きの推敲・送信は Cursor／yoritoori。
      </p>
    </Shell>
  );
}
