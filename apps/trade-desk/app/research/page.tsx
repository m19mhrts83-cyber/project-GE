import Shell from "@/components/Shell";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

function ageLabel(iso: string | null): string {
  if (!iso) return "—";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso.slice(0, 10);
  const days = Math.floor((Date.now() - t) / 86400000);
  if (days <= 0) return "今日";
  if (days === 1) return "昨日";
  return `${days}日前`;
}

export default async function ResearchPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { data: rows } = await supabase
    .from("trade_research")
    .select("fetched_at, source, topic, summary, url")
    .order("fetched_at", { ascending: false })
    .limit(40);

  const oldest = rows?.[rows.length - 1]?.fetched_at ?? null;
  const stale =
    oldest != null && Date.now() - Date.parse(String(oldest)) > 14 * 86400000;

  return (
    <Shell active="/research" email={user?.email ?? null}>
      <h1>リサーチ</h1>
      <p className="sub">
        Tavily / ChatGPT 週次の蓄積。画面は API を呼びません（オフライン可）。
      </p>
      {stale ? (
        <p className="warn">
          直近の蓄積が古いです。オンラインのとき
          <code> --tavily </code>
          でキャッシュを更新してください。
        </p>
      ) : null}
      <div className="card">
        {(rows ?? []).length === 0 ? (
          <p className="meta">まだありません。週次取込か inbox 横流しを待ってください。</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>鮮度</th>
                <th>ソース</th>
                <th>分野</th>
                <th>要約</th>
              </tr>
            </thead>
            <tbody>
              {(rows ?? []).map((r, i) => (
                <tr key={`${r.fetched_at}-${r.topic}-${i}`}>
                  <td>{ageLabel(r.fetched_at)}</td>
                  <td>{r.source}</td>
                  <td>{r.topic}</td>
                  <td className="meta">
                    {(r.summary || "").slice(0, 220)}
                    {r.url ? (
                      <>
                        {" "}
                        <a href={r.url} target="_blank" rel="noopener noreferrer">
                          出典
                        </a>
                      </>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </Shell>
  );
}
