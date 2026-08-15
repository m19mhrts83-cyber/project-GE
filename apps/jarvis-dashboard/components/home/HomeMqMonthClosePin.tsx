import { createClient } from "@/lib/supabase/server";
import { KURASHIFT_URL } from "@/lib/nav";
import {
  mqMonthCloseNotice,
  parseMqAutoRefresh,
  parseMqMonthCloseAck,
  previousCalendarMonth,
} from "@/lib/mqMonthCloseNotice";
import MqMonthCloseAckButton from "@/components/home/MqMonthCloseAckButton";

function parseMetaValue(raw: unknown): Record<string, unknown> {
  if (raw == null) return {};
  if (typeof raw === "object") return raw as Record<string, unknown>;
  if (typeof raw === "string") {
    try {
      const p = JSON.parse(raw);
      return p && typeof p === "object" ? (p as Record<string, unknown>) : {};
    } catch {
      return {};
    }
  }
  return {};
}

/** ホーム最上段: MQ月次まとめ促し（1〜10日） */
export default async function HomeMqMonthClosePin() {
  const supabase = await createClient();
  const { data: metas } = await supabase
    .from("sync_meta")
    .select("key, value")
    .in("key", ["mq_month_close", "mq_monthly_refresh"]);

  const byKey = new Map((metas ?? []).map((r) => [r.key, r.value]));
  const acked = parseMqMonthCloseAck(parseMetaValue(byKey.get("mq_month_close")));
  const autoRefresh = parseMqAutoRefresh(
    parseMetaValue(byKey.get("mq_monthly_refresh"))
  );
  const target = previousCalendarMonth();
  const nextMonthStart = (() => {
    const [y, m] = target.split("-").map(Number);
    const n = new Date(Date.UTC(y, m, 1));
    return `${n.getUTCFullYear()}-${String(n.getUTCMonth() + 1).padStart(2, "0")}-01`;
  })();

  const { count } = await supabase
    .from("kurashift_mq_period_facts")
    .select("id", { count: "exact", head: true })
    .eq("scenario_kind", "actual")
    .gte("period_month", `${target}-01`)
    .lt("period_month", nextMonthStart);

  const notice = mqMonthCloseNotice({
    acked,
    hasFacts: (count ?? 0) > 0,
    autoRefresh,
  });
  if (!notice.show) return null;

  const href = `${KURASHIFT_URL}${notice.hrefPath}`;

  return (
    <div
      className="card"
      style={{
        marginBottom: 12,
        borderColor: "var(--accent)",
        background: "color-mix(in srgb, var(--accent) 8%, transparent)",
      }}
    >
      <header>
        <span className="lvl">info</span>
        <strong>{notice.title}</strong>
      </header>
      {notice.statusLabel ? (
        <p className="meta" style={{ marginTop: 4 }}>
          状態: {notice.statusLabel}
        </p>
      ) : null}
      <p className="meta" style={{ marginTop: 6 }}>
        {notice.body}
      </p>
      <div style={{ marginTop: 10, display: "flex", gap: 8, flexWrap: "wrap" }}>
        <a className="btn primary" href={href} target="_blank" rel="noreferrer">
          MQ会計評価を開く
        </a>
        <MqMonthCloseAckButton month={notice.targetMonth} />
      </div>
    </div>
  );
}
