import Shell from "@/components/Shell";
import QueueClient, { type QueueRow } from "@/components/QueueClient";
import { wakeDueSnoozes } from "@/app/actions/triage";
import {
  type HomeLevel,
  mailPriorityToLevel,
  watchSortKey,
} from "@/lib/homeLevels";
import { createClient } from "@/lib/supabase/server";
import { watchHref } from "@/components/home/homeHelpers";
import { isOpsEphemeralId, opsWatchVisibleOnHome } from "@/lib/opsWatch";
import { zaimWatchVisibleOnHome } from "@/lib/zaimWatchPin";

export default async function QueuePage() {
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
      if (isOpsEphemeralId(String(w.id))) {
        return opsWatchVisibleOnHome(w);
      }
      const pl =
        w.payload && typeof w.payload === "object"
          ? (w.payload as Record<string, unknown>)
          : {};
      if (w.id === "zaim_quality") {
        if (zaimWatchVisibleOnHome(pl)) return true;
        return w.level !== "ok";
      }
      if (
        w.id === "etc_mileage" ||
        w.id === "vpoint" ||
        w.id === "rent_step" ||
        w.id === "cursor_pro_plus_downgrade"
      ) {
        if (pl.show_banner === true) return true;
      }
      return w.level !== "ok";
    })
    .sort((a, b) => {
      if (a.id === "cursor_pro_plus_downgrade") return -1;
      if (b.id === "cursor_pro_plus_downgrade") return 1;
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

  const items: QueueRow[] = [];
  for (const m of partnerMails) {
    items.push({
      key: `mail-${m.id}`,
      kind: "mail",
      id: m.id,
      href: `/mail/${encodeURIComponent(m.id)}`,
      level: mailPriorityToLevel(m.priority),
      title: m.partner || m.from_email || "パートナー",
      detail: m.subject || "（件名なし）",
    });
  }
  for (const w of attentionWatch) {
    const level = (
      ["attention", "warn", "info"].includes(w.level) ? w.level : "info"
    ) as HomeLevel;
    const { href, external } = watchHref(String(w.id));
    items.push({
      key: `watch-${w.id}`,
      kind: "watch",
      id: String(w.id),
      href,
      external,
      level,
      title: w.title || String(w.id),
      detail: (w.summary || "").replace(/\s+/g, " ").trim().slice(0, 120),
    });
  }

  return (
    <Shell active="/queue">
      <h1>処理キュー</h1>
      <p className="sub">
        パートナー未読 → 要確認ウォッチの順に1件ずつ。送信は詳細の確認モーダルのみ（ゲート維持）。
      </p>
      <QueueClient initialItems={items} />
    </Shell>
  );
}
