import {
  LEVEL_LABEL,
  HomeLevel,
  mailPriorityToLevel,
  watchSortKey,
} from "@/lib/homeLevels";
import { createClient } from "@/lib/supabase/server";
import { wakeDueSnoozes } from "@/app/actions/triage";
import { watchHref } from "./homeHelpers";

type QueueItem = {
  key: string;
  href: string;
  external?: boolean;
  level: HomeLevel;
  title: string;
  detail: string;
};

/** ホーム最上段: 今やるべき件数の要約 */
export default async function HomeTodayQueue() {
  await wakeDueSnoozes();
  const supabase = await createClient();

  const [{ data: watchRows }, { data: mailRows }] = await Promise.all([
    supabase.from("watch_status").select("*").eq("status", "active"),
    supabase
      .from("triage_items")
      .select(
        "id,lane,kind,status,partner,folder,subject,received_at,summary,priority,from_email",
      )
      .eq("status", "pending")
      .neq("kind", "activity")
      .order("received_at", { ascending: false })
      .limit(40),
  ]);

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

  const mails = (mailRows || []).slice().sort((a, b) => {
    const la = mailPriorityToLevel(a.priority);
    const lb = mailPriorityToLevel(b.priority);
    const order = { attention: 0, warn: 1, info: 2 } as const;
    return order[la] - order[lb];
  });
  const partnerMails = mails.filter((m) => m.lane === "partner");
  const attentionWatch = watchNeed.filter((w) => w.level === "attention");

  const items: QueueItem[] = [];
  for (const m of partnerMails.slice(0, 4)) {
    const level = mailPriorityToLevel(m.priority);
    items.push({
      key: `mail-${m.id}`,
      href: `/mail/${encodeURIComponent(m.id)}`,
      level,
      title: m.partner || m.from_email || "パートナー",
      detail: m.subject || "（件名なし）",
    });
  }
  for (const w of attentionWatch.slice(0, 4)) {
    const level = (
      ["attention", "warn", "info"].includes(w.level) ? w.level : "info"
    ) as HomeLevel;
    const { href, external } = watchHref(String(w.id));
    items.push({
      key: `watch-${w.id}`,
      href,
      external,
      level,
      title: w.title || String(w.id),
      detail: (w.summary || "").replace(/\s+/g, " ").trim().slice(0, 80),
    });
  }

  const total =
    partnerMails.length +
    attentionWatch.length +
    watchNeed.filter((w) => w.level === "warn").length;

  return (
    <section className="today-queue" aria-label="今日のキュー">
      <div className="today-queue-head">
        <h2 className="today-queue-title">今日のキュー</h2>
        <p className="today-queue-sub">
          {total === 0
            ? "いま手を動かす案件はありません"
            : `パートナー未読 ${partnerMails.length} · 要確認ウォッチ ${attentionWatch.length}`}
        </p>
      </div>
      {items.length === 0 ? (
        <p className="empty" style={{ margin: 0 }}>
          優先キューは空です。下のバンドで全体を確認できます。
        </p>
      ) : (
        <ul className="today-queue-list">
          {items.map((it) => (
            <li key={it.key}>
              <a
                href={it.href}
                className={`today-queue-item level-${it.level}`}
                {...(it.external
                  ? { target: "_blank", rel: "noopener noreferrer" }
                  : {})}
              >
                <span className="lvl">{LEVEL_LABEL[it.level]}</span>
                <span className="today-queue-main">
                  <strong>{it.title}</strong>
                  <span className="today-queue-detail">{it.detail}</span>
                </span>
                <span className="mail-chevron" aria-hidden>
                  ›
                </span>
              </a>
            </li>
          ))}
        </ul>
      )}
      <div className="today-queue-links">
        <a href="/queue" className="home-more">
          処理キュー →
        </a>
        <a href="/partner" className="home-more">
          パートナー →
        </a>
        <a href="/situation" className="home-more">
          状況ウォッチ →
        </a>
      </div>
    </section>
  );
}
