import Shell from "@/components/Shell";
import { createClient } from "@/lib/supabase/server";
import { formatJstYmdHm } from "@/lib/formatJst";
import AdvisoryExtraForm from "@/components/AdvisoryExtraForm";
import { monthLabel, monthRows, parseAdvisoryFee, parseForceMonthly, type ForceMonthly } from "@/lib/forceMonthly";
import { parseVision } from "@/lib/vision";
import { FORCE, POLICY_LEAD, POLICY_TITLE, STRATEGY, TACTICS, UNDECIDED, type PolicyItem } from "@/lib/policyText";

export const dynamic = "force-dynamic";

const COLORS: Record<string, string> = {
  claude: "#c2410c",
  cursor: "#0e7490",
  chatgpt: "#15803d",
  gcloud: "#6d28d9",
  supabase: "#a16207",
  todoist: "#be185d",
  slack: "#475569",
  notion: "#64748b",
};

function yen(n: number) {
  return `¥${Math.round(n).toLocaleString("ja-JP")}`;
}

function Items({ list }: { list: PolicyItem[] }) {
  return (
    <section className="card" style={{ padding: "4px 14px" }}>
      {list.map((it) => (
        <div key={it.id} style={{ display: "flex", gap: 10, padding: "9px 0", borderBottom: "1px solid var(--line)" }}>
          <strong style={{ minWidth: 34 }}>{it.id}</strong>
          <div>
            <div>{it.text}</div>
            {it.sub?.map((s) => (
              <div key={s} className="meta" style={{ marginTop: 4 }}>
                {s}
              </div>
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}

function Chart({ p }: { p: ForceMonthly }) {
  const W = 340;
  const H = 190;
  const padL = 40;
  const padB = 22;
  const padT = 8;
  const totals = p.months.map((ym) =>
    Object.values(p.amounts[ym] || {}).reduce((a, b) => a + b, 0),
  );
  const max = Math.max(1, ...totals);
  const top = Math.ceil(max / 5000) * 5000;
  const plotH = H - padB - padT;
  const slot = (W - padL) / p.months.length;
  const bw = Math.min(26, slot * 0.7);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="AI と基盤の月ごとの支出（積み上げ）" style={{ width: "100%", height: "auto" }}>
      {[0, 0.5, 1].map((f) => {
        const y = padT + plotH * (1 - f);
        return (
          <g key={f}>
            <line x1={padL} x2={W} y1={y} y2={y} stroke="var(--line)" strokeWidth={1} />
            <text x={padL - 4} y={y + 3} textAnchor="end" fontSize={9} fill="var(--muted)">
              {Math.round((top * f) / 1000)}k
            </text>
          </g>
        );
      })}
      {p.months.map((ym, i) => {
        let acc = 0;
        const x = padL + slot * i + (slot - bw) / 2;
        return (
          <g key={ym}>
            {p.services.map((s) => {
              const v = p.amounts[ym]?.[s.id] || 0;
              if (!v) return null;
              const h = (v / top) * plotH;
              const y = padT + plotH - ((acc + v) / top) * plotH;
              acc += v;
              return <rect key={s.id} x={x} y={y} width={bw} height={h} fill={COLORS[s.id] || "#888"} />;
            })}
            <text x={x + bw / 2} y={H - 8} textAnchor="middle" fontSize={9} fill="var(--muted)">
              {Number(ym.slice(5, 7))}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export default async function PolicyPage() {
  const supabase = await createClient();
  const { data: metas } = await supabase
    .from("sync_meta")
    .select("key,value,updated_at")
    .in("key", ["force_monthly", "advisory_fee", "vision"]);
  const val = (k: string) => (metas || []).find((m) => m.key === k)?.value as string | undefined;
  const p = parseForceMonthly(val("force_monthly"));
  const fee = parseAdvisoryFee(val("advisory_fee"));
  const vision = parseVision(val("vision"));
  const rows = p ? monthRows(p, fee) : [];

  return (
    <Shell active="/policy">
      <h1>方針</h1>
      <p className="sub">{POLICY_TITLE}</p>
      {POLICY_LEAD.map((l) => (
        <p key={l} className="meta" style={{ margin: "2px 0" }}>
          {l}
        </p>
      ))}

      {vision && (
        <>
          <h2>ビジョン（育てていく）</h2>
          <section className="card" style={{ padding: "4px 14px" }}>
            {vision.items.map((it) => (
              <div key={it.id} style={{ display: "flex", gap: 10, padding: "9px 0", borderBottom: "1px solid var(--line)" }}>
                <strong style={{ minWidth: 34 }}>{it.id}</strong>
                <div style={{ minWidth: 0, overflowWrap: "anywhere", lineHeight: 1.6 }}>
                  <div>{it.text}</div>
                  {it.sub.map((s) => (
                    <div key={s} className="meta" style={{ marginTop: 4 }}>
                      ・{s}
                    </div>
                  ))}
                </div>
              </div>
            ))}
            {vision.notes.map((n) => (
              <p key={n} className="meta" style={{ margin: "8px 0" }}>
                {n}
              </p>
            ))}
          </section>
        </>
      )}

      <h2>戦略</h2>
      <Items list={STRATEGY} />

      <h2>戦術</h2>
      <Items list={TACTICS} />

      <h2>戦力</h2>
      <p className="meta" style={{ marginBottom: 8 }}>月単位で見直す・松野さんが選ぶ</p>
      <Items list={FORCE} />

      <h2>戦力の推移（月ごと）</h2>
      <p className="meta" style={{ marginBottom: 10 }}>
        かけているお金（F3）。Zaim 2026年度の記録から、AI と基盤の支出を月ごとに集めた値です。
        {p ? ` 最終更新 ${formatJstYmdHm(p.generated_at)}` : ""}
      </p>
      {!p ? (
        <p className="meta">
          まだ値がありません。Mac で <code>python3 scripts/jarvis_force_monthly.py --push</code> を実行すると出ます。
        </p>
      ) : (
        <>
          <section className="card" style={{ padding: 12 }}>
            <p className="billing-summary-kicker">月ごとの支出（積み上げ）</p>
            <Chart p={p} />
            <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 12px", marginTop: 6 }}>
              {p.services.map((s) => (
                <span key={s.id} className="meta" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                  <span style={{ width: 10, height: 10, background: COLORS[s.id] || "#888", display: "inline-block", borderRadius: 2 }} />
                  {s.label}
                </span>
              ))}
            </div>
          </section>

          <h3>サービスごとの表（円）</h3>
          <div className="prop-event-table-wrap">
            <table className="prop-event-table">
              <thead>
                <tr>
                  <th>月</th>
                  {p.services.map((s) => (
                    <th key={s.id} style={{ whiteSpace: "nowrap" }}>{s.label}</th>
                  ))}
                  <th>合計</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.ym}>
                    <td style={{ whiteSpace: "nowrap" }}>{monthLabel(r.ym)}</td>
                    {p.services.map((s) => (
                      <td key={s.id} style={{ textAlign: "right" }}>
                        {p.amounts[r.ym]?.[s.id] ? Math.round(p.amounts[r.ym][s.id]).toLocaleString("ja-JP") : "–"}
                      </td>
                    ))}
                    <td style={{ textAlign: "right" }}><strong>{r.total.toLocaleString("ja-JP")}</strong></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="meta" style={{ paddingLeft: 18 }}>
            <li>Google Cloud は前払いなので「補充額」です。使った量ではありません。実際の使用量は管理画面で見ます。</li>
            <li>年額払い（Todoist）は払った月から12か月で割った月割りです。Slack は年額かどうか未確認のため、払った月に入れています。</li>
            <li>Cursor は月額のほかに使った分の追加請求も入っています。</li>
          </ul>

          <h2>AI 顧問料との見合い</h2>
          <p className="meta" style={{ marginBottom: 10 }}>
            顧問料は Zaim からは拾えないため、「固定分（設定値）＋改修対応などの追加費用（月ごとに入力）」で出します。
            見合いは、顧問料（固定＋追加）と、AI＋基盤の支出を並べた差と比率です（比率＝支出 ÷ 顧問料）。
          </p>
          {!fee || fee.fixed_yen <= 0 ? (
            <p className="meta">固定分がまだ設定されていません。</p>
          ) : (
            <p className="meta">固定分は設定済みです（{fee.fixed_from ? `${monthLabel(fee.fixed_from)}分から` : "開始月は未設定"}）。</p>
          )}
          <div className="prop-event-table-wrap">
            <table className="prop-event-table">
              <thead>
                <tr>
                  <th>月</th>
                  <th>固定</th>
                  <th>追加</th>
                  <th>顧問料</th>
                  <th>AI＋基盤</th>
                  <th>差</th>
                  <th>比率</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.ym}>
                    <td>{monthLabel(r.ym)}</td>
                    <td style={{ textAlign: "right" }}>{r.fixed == null ? "–" : yen(r.fixed)}</td>
                    <td style={{ textAlign: "right" }}>{r.extra == null ? "–" : yen(r.extra)}</td>
                    <td style={{ textAlign: "right" }}>{r.income == null ? "–" : yen(r.income)}</td>
                    <td style={{ textAlign: "right" }}>{yen(r.total)}</td>
                    <td style={{ textAlign: "right" }}>{r.diff == null ? "–" : yen(r.diff)}</td>
                    <td style={{ textAlign: "right" }}>{r.ratioPct == null ? "–" : `${r.ratioPct.toFixed(1)}%`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="meta">「–」は、その月に入力が無いことを示します。差は 顧問料 − (AI＋基盤) です。</p>
          <AdvisoryExtraForm months={rows.map((r) => ({ ym: r.ym, label: monthLabel(r.ym), current: r.extra }))} />

          <h2>使える量（詰まり）</h2>
          {p.usage ? (
            <div className="prop-event-table-wrap">
              <table className="prop-event-table">
                <thead>
                  <tr>
                    <th>月</th>
                    <th>枠切れの日数</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.ym}>
                      <td>{monthLabel(r.ym)}</td>
                      <td>{r.blockedDays == null ? "未" : `${r.blockedDays}日`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="meta">
              未。ai-usage には週・月ごとの最大使用率の記録はありますが、枠切れの日数はまだ残していません。記録が溜まったらここに月ごとに並べます（AI 使用量の画面で最大値は見られます）。
            </p>
          )}
        </>
      )}

      <h2>まだ決まっていないこと</h2>
      <section className="card" style={{ padding: "8px 14px" }}>
        <ul style={{ margin: 0, paddingLeft: 18 }}>
          {UNDECIDED.map((u) => (
            <li key={u} style={{ padding: "3px 0" }}>{u}</li>
          ))}
        </ul>
      </section>
    </Shell>
  );
}
