import Shell from "@/components/Shell";
import EnqueueJobButton from "@/components/EnqueueJobButton";
import { createClient } from "@/lib/supabase/server";
import { fmtYen } from "@/lib/format";
import {
  INSURANCE_ORDER,
  compareToReference,
  fundSummary,
  loadInsuranceAllocations,
} from "@/lib/insuranceAllocations";

export const dynamic = "force-dynamic";

/** KURASHIFT Core 口座（週次で揃えたい正） */
const CORE_IDS = [
  "sony_life",
  "sony_life_chikage",
  "prudential_life",
  "prudential_life_chikage",
  "bloomo",
  "sbi_index",
  "akatsuki_bond",
  "mhi_stock",
  "axa_life",
] as const;

const LOAN_IDS = [
  "sony_life_policy_loan",
  "sony_life_chikage_policy_loan",
  "prudential_life_policy_loan",
  "prudential_life_chikage_policy_loan",
] as const;

export default async function PortfolioPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { data: accounts } = await supabase
    .from("portfolio_accounts")
    .select("id, name, kind, institution, ingest")
    .eq("active", true)
    .order("id");
  const { data: snaps } = await supabase
    .from("portfolio_snapshots")
    .select("account_id, as_of, value_jpy, source")
    .order("as_of", { ascending: false })
    .limit(120);
  const { data: advisorNotes } = await supabase
    .from("advisor_notes")
    .select("advisor, note_date, body")
    .eq("advisor", "ishikawa")
    .order("note_date", { ascending: false })
    .limit(1);

  const latest = new Map<
    string,
    { as_of: string; value_jpy: number; source: string | null }
  >();
  for (const row of snaps ?? []) {
    if (!latest.has(row.account_id)) {
      latest.set(row.account_id, {
        as_of: row.as_of,
        value_jpy: Number(row.value_jpy),
        source: row.source,
      });
    }
  }

  const alloc = loadInsuranceAllocations();
  const refId = alloc.reference_account || "axa_life";
  const refFunds = alloc.accounts[refId]?.funds || [];
  const ishikawa = advisorNotes?.[0];

  const insuranceRows = INSURANCE_ORDER.map((id) => {
    const acc = (accounts ?? []).find((a) => a.id === id);
    const conf = alloc.accounts[id] || {};
    const s = latest.get(id);
    const value =
      s?.value_jpy ??
      (typeof conf.value_jpy === "number" ? conf.value_jpy : null);
    return {
      id,
      name: conf.label || acc?.name || id,
      isRef: id === refId,
      value,
      snapAsOf: s?.as_of ?? null,
      monthly: conf.monthly_yen ?? null,
      fundsText: fundSummary(conf.funds),
      vsAxa: compareToReference(refFunds, conf.funds, id === refId),
      source: conf.source || "pending",
      asOf: conf.as_of || s?.as_of || null,
    };
  });

  const coreRows = CORE_IDS.map((id) => {
    const acc = (accounts ?? []).find((a) => a.id === id);
    const s = latest.get(id);
    const ok = Boolean(s && s.value_jpy > 0);
    return {
      id,
      name: acc?.name || id,
      ok,
      snap: s,
    };
  });
  const coreOk = coreRows.filter((r) => r.ok).length;

  const loanRows = LOAN_IDS.map((id) => {
    const acc = (accounts ?? []).find((a) => a.id === id);
    const s = latest.get(id);
    return {
      id,
      name: acc?.name || id,
      ok: Boolean(s),
      snap: s,
    };
  });
  const loanTotal = loanRows.reduce(
    (sum, r) => sum + (r.snap?.value_jpy ?? 0),
    0
  );

  return (
    <Shell active="/portfolio" email={user?.email ?? null}>
      <h1>資産</h1>
      <p className="sub">
        週次スクレイプ／Zaim から入れたスナップショット。ログインは{" "}
        <a href="/settings">設定</a> から。
      </p>

      <EnqueueJobButton
        jobType="portfolio_weekly"
        title="資産週次（クラウドのみ）"
        payload={{}}
        label="週次スナップをキュー"
      />

      <div className="card">
        <header>
          <span className="lvl">生命保険（評価＋積立配分）</span>
          <strong>アクサ＝IFA正</strong>
        </header>
        <p className="meta">
          特別勘定の参考はアクサ（石川さん反映）。他社は対アクサ差分。月額・配分％は未確認なら
          pending／スクレイプ失敗時は前回 snap。
          {alloc.snap_updated_at
            ? ` snap更新: ${alloc.snap_updated_at}`
            : ""}
        </p>
        {ishikawa?.body ? (
          <p className="meta" style={{ marginTop: "0.5rem" }}>
            IFA（{ishikawa.note_date}）: {ishikawa.body}
          </p>
        ) : alloc.advisor?.policy ? (
          <p className="meta" style={{ marginTop: "0.5rem" }}>
            IFA: {alloc.advisor.policy}
          </p>
        ) : null}
        <table>
          <thead>
            <tr>
              <th>口座</th>
              <th>評価</th>
              <th>月額</th>
              <th>配分</th>
              <th>対アクサ</th>
              <th>source</th>
            </tr>
          </thead>
          <tbody>
            {insuranceRows.map((r) => (
              <tr key={r.id}>
                <td>
                  {r.name}
                  {r.isRef ? (
                    <div className="meta">参考（正）</div>
                  ) : null}
                </td>
                <td>
                  {r.value != null ? fmtYen(r.value) : "— 未取得"}
                  {r.snapAsOf ? (
                    <div className="meta">{r.snapAsOf}</div>
                  ) : null}
                </td>
                <td>
                  {r.monthly != null ? fmtYen(r.monthly) : "—"}
                </td>
                <td>
                  {r.fundsText}
                  {r.asOf ? <div className="meta">{r.asOf}</div> : null}
                </td>
                <td>{r.vsAxa}</td>
                <td>{r.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <header>
          <span className="lvl">保険借入（契約者貸付）</span>
          <strong>{fmtYen(loanTotal)}</strong>
        </header>
        <p className="meta">
          不動産購入の頭金枠把握用。解約返戻と同ログインで取得（ソニー）／PRUは手登録可。
        </p>
        <table>
          <thead>
            <tr>
              <th>口座</th>
              <th>借入残高</th>
              <th>日付</th>
            </tr>
          </thead>
          <tbody>
            {loanRows.map((r) => (
              <tr key={r.id}>
                <td>{r.name}</td>
                <td>{r.snap ? fmtYen(r.snap.value_jpy) : "— 未取得"}</td>
                <td>{r.snap?.as_of ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <header>
          <span className="lvl">Core 網羅</span>
          <strong>
            {coreOk}/{coreRows.length}
          </strong>
        </header>
        <p className="meta">
          評価が取れた口座数。未取得は env 登録または Playwright 取得が必要です。
        </p>
        <table>
          <thead>
            <tr>
              <th>Core</th>
              <th>状態</th>
              <th>評価</th>
              <th>日付</th>
            </tr>
          </thead>
          <tbody>
            {coreRows.map((r) => (
              <tr key={r.id}>
                <td>{r.name}</td>
                <td>{r.ok ? "✅" : "— 未取得"}</td>
                <td>{r.snap ? fmtYen(r.snap.value_jpy) : "—"}</td>
                <td>{r.snap?.as_of ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <header>
          <span className="lvl">全口座</span>
          <strong>スナップショット</strong>
        </header>
        <table>
          <thead>
            <tr>
              <th>口座</th>
              <th>種別</th>
              <th>評価</th>
              <th>日付</th>
              <th>ソース</th>
            </tr>
          </thead>
          <tbody>
            {(accounts ?? []).map((a) => {
              const s = latest.get(a.id);
              return (
                <tr key={a.id}>
                  <td>
                    {a.name}
                    <div className="meta">{a.institution}</div>
                  </td>
                  <td>{a.kind}</td>
                  <td>{s ? fmtYen(s.value_jpy) : "—"}</td>
                  <td>{s?.as_of ?? "—"}</td>
                  <td>{s?.source ?? a.ingest}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}
