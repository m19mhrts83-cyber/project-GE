import { createServiceClient } from "@/lib/supabase/admin";
import { loopwareHref } from "@/lib/loopwareLink";
import { deskWorthy } from "@/lib/deskWorthy";

/**
 * ループウェアの入口（ホーム）。判断待ちの件数と、今週の判断ログの粒だけ出す。
 * 判断そのものは loopware の判断デスクで（ここでは押さない）。
 */
const LABEL: Record<string, string> = { take: "採った", ng: "見送った", hesitate: "迷った", none: "未判断" };

function obj(x: unknown): Record<string, unknown> {
  return x && typeof x === "object" && !Array.isArray(x) ? (x as Record<string, unknown>) : {};
}

export default async function HomeLoopwareBand() {
  const sb = createServiceClient();
  if (!sb) return null;
  const since = new Date(Date.now() - 7 * 86400_000).toISOString();
  const [pend, week] = await Promise.all([
    sb
      .from("triage_items")
      .select("id,lane,kind,subject,from_email,original_body,payload")
      .eq("status", "pending")
      .in("lane", ["partner", "general"])
      .limit(600),
    sb.from("owner_decisions").select("payload").gte("decided_at", since).limit(2000),
  ]);
  const pendRows = (pend.data || []).filter((r) => !String(r.id || "").startsWith("re-vendor-") && !obj(r.payload).re_vendor_reply);
  // デスクに出るのは人が判断するものだけ。自動のお知らせ・メルマガは「その他メール」のまとめへ
  const n = pendRows.filter(deskWorthy).length;
  const rest = pendRows.length - n;
  const tally: Record<string, number> = { take: 0, ng: 0, hesitate: 0, none: 0 };
  for (const r of week.data || []) {
    const o = String(((r.payload || {}) as Record<string, unknown>).outcome || "");
    if (o in tally) tally[o] += 1;
  }
  const total = Object.values(tally).reduce((a, b) => a + b, 0);
  return (
    <article className="card" style={{ marginBottom: 16 }}>
      <header>
        <span className="lvl">判断</span>
        <strong>ループウェア</strong>
      </header>
      <p className="sum" style={{ margin: "6px 0 12px" }}>
        判断待ち <b>{n}</b> 件{rest ? `（ほか自動のお知らせ ${rest} 件は「その他メール」へ）` : ""} ・ 今週のログ {total} 粒
        {total
          ? `（${Object.entries(tally)
              .filter(([, v]) => v)
              .map(([k, v]) => `${LABEL[k]}${v}`)
              .join("・")}）`
          : ""}
      </p>
      <a className="btn primary" href={loopwareHref("/desk", { from: "dashboard" })} target="_blank" rel="noopener noreferrer">
        判断デスクを開く ↗
      </a>
    </article>
  );
}
