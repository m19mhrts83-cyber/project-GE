import Link from "next/link";
import Shell from "@/components/Shell";
import { createServiceClient } from "@/lib/supabase/admin";
import {
  PARTNER_ACTIONS,
  PARTNER_ACTION_LABEL,
  decisionsForPartner,
  reasonLabelsOf,
  summarizeByPartner,
  type PartnerAction,
  type PartnerDecisionRow,
} from "@/lib/partnerDecisions";
import { md } from "@/lib/mailInsights";

/**
 * パートナー別の判断（見送り・Todoist・後回し）。2026-11-27 松野さん了承（116・大佐 件127）。
 * ログイン必須のダッシュボード内だけで見せる（公開しない）。読むだけ・AI は使わない。
 * 理由は本人が押した理由タグだけ。押していない判断は「理由なし」。
 */
export const dynamic = "force-dynamic";
export const metadata = { title: "パートナー別の判断｜Jarvis" };

const DAYS = 90;

async function load(): Promise<{ rows: PartnerDecisionRow[]; error: string | null } | null> {
  const sb = createServiceClient();
  if (!sb) return null;
  const since = new Date(Date.now() - DAYS * 86400_000).toISOString();
  const { data, error } = await sb
    .from("owner_decisions")
    .select("id,decided_at,action,partner,subject,payload")
    .eq("surface", "triage")
    .in("action", [...PARTNER_ACTIONS])
    .gte("decided_at", since)
    .order("decided_at", { ascending: false })
    .limit(5000);
  return { rows: (data || []) as PartnerDecisionRow[], error: error?.message || null };
}

export default async function PartnerDecisionsPage({
  searchParams,
}: {
  searchParams: Promise<{ partner?: string; action?: string }>;
}) {
  const sp = await searchParams;
  const d = await load();
  if (!d) {
    return (
      <Shell active="/mail">
        <h1>パートナー別の判断</h1>
        <p className="empty">Supabase が未設定のため読めません。</p>
      </Shell>
    );
  }
  const key = String(sp.partner || "").trim();
  const actionFilter = PARTNER_ACTIONS.includes(sp.action as PartnerAction) ? (sp.action as PartnerAction) : null;
  const summary = summarizeByPartner(d.rows);
  const picked = key ? summary.find((s) => s.key === key.toLowerCase()) : null;
  let list = key ? decisionsForPartner(d.rows, key) : [];
  if (actionFilter) list = list.filter((r) => r.action === actionFilter);

  return (
    <Shell active="/mail">
      <div className="mi">
        <header className="mi-head">
          <span className="mi-eyebrow">メール</span>
          <h1>パートナー別の判断</h1>
          <p className="sub">
            直近{DAYS}日の見送り・Todoist・後で、を送り手ごとに引けます。理由は、押したものだけを出します（押していないものは「理由なし」）。
            {d.error ? ` 一部読めませんでした（${d.error}）。` : ""}
            {" "}
            <Link href="/mail">メールの振り返りへ</Link>
          </p>
        </header>

        <section aria-label="パートナー一覧">
          {summary.length ? (
            <table>
              <thead>
                <tr>
                  <th>送り手</th>
                  {PARTNER_ACTIONS.map((a) => (
                    <th key={a}>{PARTNER_ACTION_LABEL[a]}</th>
                  ))}
                  <th>理由あり</th>
                  <th>直近</th>
                </tr>
              </thead>
              <tbody>
                {summary.map((s) => (
                  <tr key={s.key}>
                    <td>
                      <Link href={`/mail/partners?partner=${encodeURIComponent(s.key)}`}>{s.name}</Link>
                    </td>
                    {PARTNER_ACTIONS.map((a) => (
                      <td key={a}>{s.counts[a] || "—"}</td>
                    ))}
                    <td>
                      {s.withReason}/{s.total}
                    </td>
                    <td>{md(s.lastAt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="empty">この期間の見送り・Todoist・後での判断はありません。</p>
          )}
        </section>

        {key ? (
          <section aria-label="判断の一覧">
            <h2>{picked?.name || key}</h2>
            <p>
              <Link href={`/mail/partners?partner=${encodeURIComponent(key)}`}>すべて</Link>
              {PARTNER_ACTIONS.map((a) => (
                <span key={a}>
                  {" ・ "}
                  <Link href={`/mail/partners?partner=${encodeURIComponent(key)}&action=${a}`}>{PARTNER_ACTION_LABEL[a]}</Link>
                </span>
              ))}
            </p>
            {list.length ? (
              <ul>
                {list.map((r) => {
                  const reasons = reasonLabelsOf(r);
                  return (
                    <li key={r.id}>
                      {md(r.decided_at)} · {PARTNER_ACTION_LABEL[r.action as PartnerAction]} ·{" "}
                      {reasons.length ? `理由: ${reasons.join("・")}` : "理由なし"}
                      {r.subject ? ` — ${String(r.subject).slice(0, 80)}` : ""}
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="empty">該当する判断はありません。</p>
            )}
          </section>
        ) : null}
      </div>
    </Shell>
  );
}
