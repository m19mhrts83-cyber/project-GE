import {
  LEVEL_LABEL,
  HomeLevel,
  watchSortKey,
} from "@/lib/homeLevels";
import { createClient } from "@/lib/supabase/server";
import { watchHref } from "./homeHelpers";

export default async function HomeWatchBand() {
  const supabase = await createClient();
  const { data: watchRows } = await supabase
    .from("watch_status")
    .select("*")
    .eq("status", "active");

  const watchNeed = (watchRows || [])
    .filter((w) => {
      const pl =
        w.payload && typeof w.payload === "object"
          ? (w.payload as Record<string, unknown>)
          : {};
      if (
        w.id === "etc_mileage" ||
        w.id === "vpoint" ||
        w.id === "rent_step" ||
        w.id === "zaim_quality" ||
        w.id === "cursor_pro_plus_downgrade" ||
        w.id === "glucon_report_due" ||
        w.id === "mobile_plan"
      ) {
        if (pl.show_banner === true) return true;
      }
      return w.level !== "ok";
    })
    .sort((a, b) => {
      const pa =
        a.payload && typeof a.payload === "object"
          ? (a.payload as Record<string, unknown>)
          : {};
      const pb =
        b.payload && typeof b.payload === "object"
          ? (b.payload as Record<string, unknown>)
          : {};
      const pinA =
        pa.pin_top === true || a.id === "cursor_pro_plus_downgrade";
      const pinB =
        pb.pin_top === true || b.id === "cursor_pro_plus_downgrade";
      if (pinA !== pinB) return pinA ? -1 : 1;
      return (
        watchSortKey(a.level) - watchSortKey(b.level) ||
        String(b.updated_at || "").localeCompare(String(a.updated_at || ""))
      );
    });

  const counts = { attention: 0, warn: 0, info: 0 };
  for (const w of watchNeed) {
    const lv = (w.level || "info") as HomeLevel;
    if (lv in counts) counts[lv] += 1;
  }

  return (
      <div className="home-band home-band-watch">
        <div className="home-band-head">
          <h2 className="home-band-title">状況ウォッチ</h2>
          <p className="home-band-sub">仕組み・還元・同期などの健康診断</p>
        </div>

        <div className="stats home-stats">
          <div className="stat level-attention">
            要確認 <strong>{counts.attention}</strong>
          </div>
          <div className="stat level-warn">
            注意 <strong>{counts.warn}</strong>
          </div>
          <div className="stat level-info">
            参考 <strong>{counts.info}</strong>
          </div>
        </div>

        <section className="home-section">
          <div className="home-section-head">
            <h3>要フォロー</h3>
            <a href="/situation" className="home-more">
              すべて →
            </a>
          </div>
          {watchNeed.length === 0 ? (
            <p className="empty">
              いま要注意の項目はありません（ok のみ、または未 push）
            </p>
          ) : (
            <div className="watch-grid">
              {watchNeed.map((it) => {
                const level = (
                  ["attention", "warn", "info"].includes(it.level)
                    ? it.level
                    : "info"
                ) as HomeLevel;
                const { href, external } = watchHref(String(it.id));
                return (
                  <a
                    key={it.id}
                    href={href}
                    className={`card watch-card level-${level}`}
                    {...(external
                      ? { target: "_blank", rel: "noopener noreferrer" }
                      : {})}
                  >
                    <header>
                      <span className="lvl">{LEVEL_LABEL[level]}</span>
                      <strong title={it.title}>{it.title}</strong>
                    </header>
                    <p className="sum">{it.summary}</p>
                    {it.source ? <p className="meta">{it.source}</p> : null}
                  </a>
                );
              })}
            </div>
          )}
        </section>
      </div>
  );
}
