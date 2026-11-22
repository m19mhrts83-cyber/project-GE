import Shell from "@/components/Shell";
import { createClient } from "@/lib/supabase/server";
import { formatJstYmdHm } from "@/lib/formatJst";
import {
  ageText,
  historyRows,
  parseAiUsage,
  splitAiSubs,
  viewRows,
  viewVerdicts,
  type AiUsageRowView,
  type AiUsageVerdict,
} from "@/lib/aiUsage";

export const dynamic = "force-dynamic";

type AiSub = { id: string; name: string; billing: string; monthly_yen: number; next_bill: string | null };

const LEVEL: Record<AiUsageVerdict["level"], { badge: string; tone: string; card: string }> = {
  ok: { badge: "余裕", tone: "ok", card: "" },
  keep: { badge: "今のプラン", tone: "warn", card: "" },
  warn: { badge: "注意", tone: "attention", card: "level-attention" },
  unknown: { badge: "判断できない", tone: "info", card: "" },
};

const HISTORY: { key: string; title: string; unit: string }[] = [
  { key: "claude.weekly", title: "Claude の週枠", unit: "週" },
  { key: "codex.weekly", title: "Codex の週枠", unit: "週" },
  { key: "cursor.monthly", title: "Cursor の月枠", unit: "月" },
];

const AGENT_ORDER = ["claude", "codex", "cursor", "antigravity"];

function fmtYen(n: number) {
  return `¥${Math.round(n).toLocaleString("ja-JP")}`;
}

function Bar({ r }: { r: AiUsageRowView }) {
  const n = r.used_percent;
  const dim = r.stale || r.resetPassed;
  const tone = n == null || dim ? "neutral" : n >= 90 ? "hot" : n >= 70 ? "warm" : "ok";
  const width = n == null ? 0 : Math.max(0, Math.min(100, n));
  return (
    <div className="cursor-usage-bar-row">
      <div className="cursor-usage-bar-label">
        <span>{r.label}</span>
        <span className="meta">
          {n == null ? "読めない" : `${Math.round(n)}%`}
          {r.resetPassed ? "（回復済みのはず）" : r.stale ? "（古い）" : ""}
        </span>
      </div>
      <div className="cursor-usage-bar-track" aria-hidden>
        <div className={`cursor-usage-bar-fill tone-${tone}`} style={{ width: `${width}%` }} />
      </div>
      <p className="meta" style={{ margin: "4px 0 0" }}>
        {r.resets_at ? `回復 ${formatJstYmdHm(r.resets_at)}` : "回復時刻なし"}
        {" · "}値は{ageText(r.ageMin)}
        {r.note ? ` · ${r.note}` : ""}
      </p>
    </div>
  );
}

export default async function AiUsagePage() {
  const supabase = await createClient();
  const [{ data: meta }, { data: subs }] = await Promise.all([
    supabase.from("sync_meta").select("key,value,updated_at").eq("key", "ai_usage_now").maybeSingle(),
    supabase
      .from("subscription_services")
      .select("id,name,billing,monthly_yen,next_bill,category,status")
      .eq("category", "ai")
      .eq("status", "active")
      .order("monthly_yen", { ascending: false }),
  ]);

  const now = Date.now();
  const p = parseAiUsage(meta?.value as string | undefined);
  const rows = p ? viewRows(p, now) : [];
  const verdicts = p ? viewVerdicts(p, rows) : [];
  const aiSubs = (subs || []) as AiSub[];
  const split = splitAiSubs(aiSubs);
  const a = p?.assumptions;

  return (
    <Shell active="/ai-usage">
      <h1>AI 使用量</h1>
      <p className="sub">
        プランを上げるか下げるかを決めるための画面。Mac が1日に数回、4者の枠を読んで写します。
        {p ? ` 最終更新 ${formatJstYmdHm(p.generated_at)}` : ""}
      </p>

      {!p ? (
        <p className="meta">
          まだ値がありません。Mac で <code>python3 scripts/jarvis_ai_usage_snapshot.py --push</code> を実行すると出ます。
        </p>
      ) : (
        <>
          <h2>いまの判断</h2>
          {verdicts.map((v) => {
            const lv = LEVEL[v.level] || LEVEL.unknown;
            return (
              <section key={v.agent} className={`billing-cursor-usage card ${lv.card}`.trim()}>
                <header className="cursor-usage-head">
                  <p className="cursor-usage-plan">{v.title}</p>
                  <span className={`cursor-usage-badge tone-${lv.tone}`}>{lv.badge}</span>
                </header>
                <p className="cursor-usage-verdict">{v.detail}</p>
              </section>
            );
          })}

          <h2>枠ごとの使用率</h2>
          {AGENT_ORDER.map((agent) => {
            const list = rows.filter((r) => r.agent === agent);
            if (!list.length) return null;
            return (
              <section key={agent} className="billing-cursor-usage card">
                <p className="billing-summary-kicker">{list[0].agent_label}</p>
                {list.map((r) => (
                  <Bar key={`${r.agent}.${r.window}`} r={r} />
                ))}
              </section>
            );
          })}

          <h2>これまでの最大値</h2>
          <p className="meta" style={{ marginBottom: 12 }}>
            枠ごとに、その週（月）で見た一番高い使用率。Mac が読んだ時点の値なので、実際より少し低いことがあります。
          </p>
          {HISTORY.map((h) => {
            const list = historyRows(p, h.key, now);
            return (
              <section key={h.key} className="billing-cursor-usage card">
                <p className="billing-summary-kicker">{h.title}</p>
                {list.length === 0 ? (
                  <p className="meta">まだ記録がありません。</p>
                ) : (
                  <table className="prop-event-table">
                    <thead>
                      <tr>
                        <th>枠の終わり</th>
                        <th>最大</th>
                        <th>状態</th>
                      </tr>
                    </thead>
                    <tbody>
                      {list.map((e) => (
                        <tr key={e.resets_at}>
                          <td>{formatJstYmdHm(e.resets_at)}</td>
                          <td>{Math.round(e.peak)}%</td>
                          <td>{e.closed ? `終わった${h.unit}` : `進行中の${h.unit}`}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </section>
            );
          })}
        </>
      )}

      <h2>いまの AI の月額</h2>
      {aiSubs.length === 0 ? (
        <p className="meta">契約の一覧が読めませんでした。「サブスク・課金」を見てください。</p>
      ) : (
        <>
          <div className="stats">
            <div className="stat">
              エージェントの道具 <strong>{fmtYen(split.toolsTotal)}</strong>
            </div>
            <div className="stat">
              基盤の維持 <strong>{fmtYen(split.baseTotal)}</strong>
            </div>
            <div className="stat">
              合計 <strong>{fmtYen(split.total)}</strong>
            </div>
          </div>
          {[
            { title: "エージェントの道具（使用量の枠がある契約）", list: split.tools, total: split.toolsTotal },
            { title: "AI エージェントの基盤を保つ契約（入力・連絡・保管など）", list: split.base, total: split.baseTotal },
          ].map((g) => (
            <section key={g.title} className="billing-cursor-usage card">
              <p className="billing-summary-kicker">{g.title}</p>
              <p className="cursor-usage-plan">小計 {fmtYen(g.total)}／月</p>
              {g.list.length === 0 ? (
                <p className="meta">該当する契約はありません。</p>
              ) : (
                <table className="prop-event-table">
                  <tbody>
                    {g.list.map((s) => (
                      <tr key={s.id}>
                        <td>{s.name}</td>
                        <td>{fmtYen(Number(s.monthly_yen || 0))}／月</td>
                        <td className="meta">{s.next_bill ? `次回 ${s.next_bill}` : ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          ))}
          <p className="meta cursor-usage-foot">
            契約の正本は <a href="/billing">サブスク・課金</a>。プランの上げ下げで動くのは「エージェントの道具」の側です。
          </p>
        </>
      )}

      <h2>目安の決め方</h2>
      <p className="meta">
        Claude の判断は「Max は Pro の約{a?.max_to_pro ?? 5}倍」という前提で、Max の週枠が
        {a?.pro_ok_below ?? 20}%未満の週が{a?.weeks_needed ?? 2}週続いたら Pro への移行を提案します。
        この線は Miss Lemon の案で、まだ確定した基準ではありません。値が
        {Math.round((a?.stale_min ?? 180) / 60)}時間より古い時は、判断を出しません。
        Claude の値はデスクトップアプリからは自動で入らないため、古い時は 設定→使用量 の数字が正です。
      </p>
    </Shell>
  );
}
