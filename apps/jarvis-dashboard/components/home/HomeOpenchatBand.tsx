import { parseOpenchatDigest } from "@/lib/openchatDigest";
import { createClient } from "@/lib/supabase/server";

export default async function HomeOpenchatBand() {
  const supabase = await createClient();
  const { data: meta } = await supabase.from("sync_meta").select("key,value");
  const metaMap = Object.fromEntries((meta || []).map((m) => [m.key, m.value]));
  const oc = parseOpenchatDigest(metaMap.openchat_digest);
  const groups = oc?.groups || [];

  return (
    <div className="home-band home-band-openchat">
      <div className="home-band-head">
        <h2 className="home-band-title">神大家オプチャまとめ</h2>
        <p className="home-band-sub">大家業に役立ちそうな直近情報（返信提案なし）</p>
      </div>
      {oc?.overview ? (
        <p className="openchat-digest-overview">{oc.overview}</p>
      ) : null}
      {groups.length === 0 ? (
        <p className="empty">
          直近の有益情報はありません。{" "}
          <a href="/openchat" className="home-more">
            オプチャ一覧 →
          </a>
        </p>
      ) : (
        <div className="watch-grid">
          {groups.map((g) => (
            <a
              key={g.slug || g.name}
              href={`/openchat/${g.slug || encodeURIComponent(g.name.replace(/\s+/g, "_"))}`}
              className="card watch-card home-openchat-card"
            >
              <header>
                <span className="lvl">有益</span>
                <strong>{g.name}</strong>
                {g.updated_at ? (
                  <span className="meta">{g.updated_at}</span>
                ) : null}
              </header>
              <ul className="openchat-group-lines">
                {(g.lines || []).slice(0, 3).map((ln, i) => (
                  <li key={i}>{ln}</li>
                ))}
              </ul>
            </a>
          ))}
        </div>
      )}
      {groups.length > 0 ? (
        <p className="home-metrics-more">
          <a href="/openchat" className="home-more">
            オプチャ一覧 →
          </a>
        </p>
      ) : null}
    </div>
  );
}
