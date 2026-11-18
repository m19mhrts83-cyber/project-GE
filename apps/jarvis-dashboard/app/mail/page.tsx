import Shell from "@/components/Shell";
import { createServiceClient } from "@/lib/supabase/admin";
import { loopwareHref } from "@/lib/loopwareLink";
import { deskWorthy } from "@/lib/deskWorthy";
import MailInsightsView, { type Learned } from "@/components/mail-insights/MailInsightsView";
import {
  DAY_MS,
  bulkMinutes,
  dailyBreakdown,
  hourly,
  insights,
  kpis,
  md,
  peakHours,
  styleStats,
  weeklyVolume,
  type Decision,
  type MailRow,
} from "@/lib/mailInsights";
import "./mail-insights.css";

/**
 * メールの振り返り（2026-11-17 松野さん決定）。
 * 処置は判断デスク（loopware /desk）で行い、ここは回答状況・傾向・学び・スタイル・気づきを見る場所。
 * 集計は開いたときに SQL で読むだけ。AI は使わない。
 */
export const dynamic = "force-dynamic";
export const metadata = { title: "メールの振り返り｜Jarvis" };

const RANGE_DAYS = 30;
const CHART_DAYS = 14;
const WEEKS = 16;
const RULE_SURFACES = ["rule_review", "triage_rule", "uiux_rule", "slide_rule"];
const RULE_SURFACE_LABEL: Record<string, string> = {
  rule_review: "メールのルール",
  triage_rule: "メールのルール",
  uiux_rule: "画面の好み",
  slide_rule: "資料の好み",
};

function obj(x: unknown): Record<string, unknown> {
  return x && typeof x === "object" && !Array.isArray(x) ? (x as Record<string, unknown>) : {};
}

async function load() {
  const sb = createServiceClient();
  if (!sb) return null;
  const now = new Date();
  const since = new Date(now.getTime() - RANGE_DAYS * DAY_MS).toISOString();
  const weeksSince = new Date(now.getTime() - (WEEKS + 1) * 7 * DAY_MS).toISOString();
  const [pend, dec, rules, mails, oldest] = await Promise.all([
    sb
      .from("triage_items")
      .select("id,lane,kind,subject,from_email,original_body,payload,created_at")
      .eq("status", "pending")
      .in("lane", ["partner", "general"])
      .limit(600),
    sb
      .from("owner_decisions")
      .select("id,decided_at,surface,action,partner,lane,final_text,edited,payload")
      .in("surface", ["triage", "triage_miss", "draft_review"])
      .gte("decided_at", since)
      .order("decided_at", { ascending: false })
      .limit(5000),
    sb
      .from("owner_decisions")
      .select("id,decided_at,surface,action,note,payload")
      .in("surface", RULE_SURFACES)
      .in("action", ["rule_accept", "rule_revert"])
      .order("decided_at", { ascending: false })
      .limit(8),
    sb
      .from("triage_items")
      .select("created_at,lane")
      .in("lane", ["partner", "general"])
      .gte("created_at", weeksSince)
      .limit(10000),
    sb.from("triage_items").select("created_at").in("lane", ["partner", "general"]).order("created_at", { ascending: true }).limit(1),
  ]);
  const [pTotal, gTotal] = await Promise.all([
    sb.from("triage_items").select("id", { count: "exact", head: true }).eq("lane", "partner"),
    sb.from("triage_items").select("id", { count: "exact", head: true }).eq("lane", "general"),
  ]);
  return {
    now,
    pending: (pend.data || []).filter((r) => !String(r.id || "").startsWith("re-vendor-") && !obj(r.payload).re_vendor_reply),
    decisions: (dec.data || []) as Decision[],
    rules: rules.data || [],
    mails: (mails.data || []) as MailRow[],
    totals: {
      partner: pTotal.count || 0,
      general: gTotal.count || 0,
      since: oldest.data?.[0]?.created_at ? md(oldest.data[0].created_at) : null,
    },
    error: dec.error?.message || pend.error?.message || null,
  };
}

export default async function MailInsightsPage() {
  const d = await load();
  if (!d) {
    return (
      <Shell active="/mail">
        <h1>メールの振り返り</h1>
        <p className="empty">Supabase が未設定のため読めません。</p>
      </Shell>
    );
  }

  const desk = d.pending.filter(deskWorthy);
  const deskPartner = desk.filter((r) => r.lane === "partner").length;
  const oldestPending = desk.reduce<string | null>((a, r) => (!a || String(r.created_at) < a ? String(r.created_at) : a), null);
  const waitDays = oldestPending ? Math.floor((d.now.getTime() - Date.parse(oldestPending)) / DAY_MS) : null;

  const bulk = bulkMinutes(d.decisions);
  const k = kpis(d.decisions, RANGE_DAYS, bulk);
  const days = dailyBreakdown(d.decisions, CHART_DAYS, d.now);
  const hours = hourly(d.decisions, bulk);
  const peaks = peakHours(hours, 3);
  const weeks = weeklyVolume(d.mails, WEEKS, d.now);
  const style = styleStats(d.decisions);
  const notes = insights({ k, weeks, peaks, totals: d.totals });
  const revise = d.decisions.filter((r) => r.surface === "draft_review" && r.action === "revise").length;

  const learned: Learned[] = [];
  for (const r of d.rules) {
    const p = obj(r.payload);
    const text = String(p.text || p.rule_line || r.note || p.rule_id || "").slice(0, 80);
    learned.push({
      at: md(String(r.decided_at)),
      title: `${RULE_SURFACE_LABEL[String(r.surface)] || "ルール"}を${r.action === "rule_accept" ? "採用" : "取り消し"}`,
      detail: text || "内容の記録なし",
      pill: r.action === "rule_accept" ? "採用済み" : "取り消し",
      tone: r.action === "rule_accept" ? "on" : "wait",
    });
  }
  if (k.missTotal) {
    learned.push({
      at: `${RANGE_DAYS}日`,
      title: `見落とし確認 ${k.missTotal} 件中 ${k.missOk} 件が「合っていた」`,
      detail: k.missTotal - k.missOk ? `外れたのは ${k.missTotal - k.missOk} 件。外れた形は土曜の週次でルール案になります` : "外れはありません",
      pill: "結果",
      tone: "on",
    });
  }
  if (k.bulk) {
    learned.push({
      at: `${RANGE_DAYS}日`,
      title: `まとめて ${k.bulk} 件を一括で判断`,
      detail: "同じ1分に10件以上押したもの。送り主ごとに、次から自動で下げる候補になります",
      pill: "ルール案",
      tone: "wait",
    });
  }
  if (revise) {
    learned.push({
      at: `${RANGE_DAYS}日`,
      title: `下書きの直しを ${revise} 回記録`,
      detail: "直しの中身は週次でまとめ、下書きの決まりに入れる候補にします",
      pill: "集計待ち",
      tone: "wait",
    });
  }

  const deskHref = loopwareHref("/desk", { from: "mail-insights" });

  return (
    <Shell active="/mail">
      <MailInsightsView
        rangeDays={RANGE_DAYS}
        chartDays={CHART_DAYS}
        weeksN={WEEKS}
        error={d.error}
        deskCount={desk.length}
        deskPartner={deskPartner}
        waitDays={waitDays}
        deskHref={deskHref}
        k={k}
        days={days}
        hours={hours}
        peaks={peaks}
        weeks={weeks}
        style={style}
        learned={learned}
        notes={notes}
      />
    </Shell>
  );
}
