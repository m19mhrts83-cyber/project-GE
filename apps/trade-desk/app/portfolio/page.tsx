import Shell from "@/components/Shell";
import EnqueueJobButton from "@/components/EnqueueJobButton";
import { createClient } from "@/lib/supabase/server";
import {
  fmtPct,
  fmtPctSigned,
  fmtYen,
  fmtYenSigned,
  gainPct,
} from "@/lib/format";
import {
  INSURANCE_ORDER,
  compareToReference,
  fundSummary,
  loadInsuranceAllocations,
} from "@/lib/insuranceAllocations";
import { fmtRatePct, loadLiabilityRates } from "@/lib/liabilityRates";
import {
  MIX_CORE,
  MIX_LABEL,
  addToMix,
  allocateInsuranceValue,
  classifyHolding,
  emptyMix,
  finalizeMix,
  fundCost,
  paidInByInsurer,
  yen,
  type HoldingFund,
} from "@/lib/portfolioMix";

export const dynamic = "force-dynamic";

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

const VARIABLE_INS = ["axa_life", "sony_life", "sony_life_chikage"] as const;
const PRU_INS = ["prudential_life", "prudential_life_chikage"] as const;

function num(v: number | string | null | undefined): number | null {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isNaN(n) ? null : n;
}

export default async function PortfolioPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const [
    { data: accounts },
    { data: snaps },
    { data: advisorNotes },
    { data: holdingsRows },
    { data: premiumRows },
    { data: liqAccounts },
    { data: liqSnaps },
  ] = await Promise.all([
    supabase
      .from("portfolio_accounts")
      .select("id, name, kind, institution, ingest")
      .eq("active", true)
      .order("id"),
    supabase
      .from("portfolio_snapshots")
      .select("account_id, as_of, value_jpy, source")
      .order("as_of", { ascending: false })
      .limit(200),
    supabase
      .from("advisor_notes")
      .select("advisor, note_date, body")
      .eq("advisor", "ishikawa")
      .order("note_date", { ascending: false })
      .limit(1),
    supabase
      .from("securities_holdings")
      .select("account_id, as_of, value_jpy, source, payload")
      .in("account_id", ["sbi_index", "bloomo", "akatsuki_bond"])
      .order("as_of", { ascending: false })
      .limit(12),
    supabase
      .from("kurashift_finance_transactions")
      .select("subcategory, expense_jpy")
      .in("subcategory", ["ソニー生命", "アクサ生命", "プルデンシャル生命"])
      .gt("expense_jpy", 0)
      .limit(8000),
    supabase
      .from("liquidity_accounts")
      .select("id, name, kind")
      .eq("active", true),
    supabase
      .from("liquidity_snapshots")
      .select("account_id, as_of, balance_jpy")
      .order("as_of", { ascending: false })
      .limit(80),
  ]);

  const latest = new Map<
    string,
    { as_of: string; value_jpy: number; source: string | null }
  >();
  const prev = new Map<string, { as_of: string; value_jpy: number }>();
  for (const row of snaps ?? []) {
    const v = Number(row.value_jpy);
    if (!latest.has(row.account_id)) {
      latest.set(row.account_id, {
        as_of: row.as_of,
        value_jpy: v,
        source: row.source,
      });
      continue;
    }
    if (!prev.has(row.account_id) && row.as_of !== latest.get(row.account_id)?.as_of) {
      prev.set(row.account_id, { as_of: row.as_of, value_jpy: v });
    }
  }

  const alloc = loadInsuranceAllocations();
  const liabilityRates = loadLiabilityRates();
  const refId = alloc.reference_account || "axa_life";
  const refFunds = alloc.accounts[refId]?.funds || [];
  const ishikawa = advisorNotes?.[0];
  const paid = paidInByInsurer(premiumRows ?? []);

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
      funds: conf.funds || [],
      fundsText: fundSummary(conf.funds),
      vsAxa: compareToReference(refFunds, conf.funds, id === refId),
      source: conf.source || "pending",
      asOf: conf.as_of || s?.as_of || null,
    };
  });

  const insTotal = insuranceRows.reduce((s, r) => s + (r.value ?? 0), 0);
  const sonyValue = insuranceRows
    .filter((r) => r.id === "sony_life" || r.id === "sony_life_chikage")
    .reduce((s, r) => s + (r.value ?? 0), 0);
  const variableValue = insuranceRows
    .filter((r) => (VARIABLE_INS as readonly string[]).includes(r.id))
    .reduce((s, r) => s + (r.value ?? 0), 0);
  const variablePaid = paid.axa + paid.sony;
  const pruValue = insuranceRows
    .filter((r) => (PRU_INS as readonly string[]).includes(r.id))
    .reduce((s, r) => s + (r.value ?? 0), 0);

  const coreRows = CORE_IDS.map((id) => {
    const acc = (accounts ?? []).find((a) => a.id === id);
    const s = latest.get(id);
    const ok = Boolean(s && s.value_jpy > 0);
    return { id, name: acc?.name || id, ok, snap: s };
  });
  const coreOk = coreRows.filter((r) => r.ok).length;

  const loanRows = LOAN_IDS.map((id) => {
    const acc = (accounts ?? []).find((a) => a.id === id);
    const s = latest.get(id);
    return { id, name: acc?.name || id, ok: Boolean(s), snap: s };
  });
  const loanTotal = loanRows.reduce(
    (sum, r) => sum + (r.snap?.value_jpy ?? 0),
    0
  );
  const sonyLoan = latest.get("sony_life_policy_loan")?.value_jpy ?? 0;

  const latestHoldings = new Map<
    string,
    {
      as_of: string;
      value_jpy: number | null;
      source: string | null;
      funds: HoldingFund[];
    }
  >();
  for (const row of holdingsRows ?? []) {
    if (latestHoldings.has(row.account_id)) continue;
    const payload = (row.payload || {}) as { funds?: HoldingFund[] };
    latestHoldings.set(row.account_id, {
      as_of: row.as_of,
      value_jpy: row.value_jpy != null ? Number(row.value_jpy) : null,
      source: row.source,
      funds: payload.funds || [],
    });
  }
  const akatsukiSnap = latest.get("akatsuki_bond");
  if (!latestHoldings.get("akatsuki_bond")?.funds.length && akatsukiSnap) {
    latestHoldings.set("akatsuki_bond", {
      as_of: akatsukiSnap.as_of,
      value_jpy: akatsukiSnap.value_jpy,
      source: akatsukiSnap.source,
      funds: [
        {
          name: "外国債券",
          value_jpy: akatsukiSnap.value_jpy,
        },
      ],
    });
  }

  const mix = emptyMix();
  const axaFunds = alloc.accounts.axa_life?.funds;
  for (const r of insuranceRows) {
    if (!(VARIABLE_INS as readonly string[]).includes(r.id) || r.value == null) {
      continue;
    }
    const funds = r.funds.length ? r.funds : axaFunds;
    for (const piece of allocateInsuranceValue(r.value, funds)) {
      addToMix(mix, piece.bucket, piece.value, null);
    }
  }
  for (const aid of ["sbi_index", "bloomo", "akatsuki_bond"] as const) {
    const h = latestHoldings.get(aid);
    for (const f of h?.funds || []) {
      const v = yen(f.value_jpy);
      if (v <= 0) continue;
      addToMix(mix, classifyHolding(f.name || "", f.code), v, fundCost(f));
    }
  }
  const mhi = latest.get("mhi_stock");
  if (mhi) addToMix(mix, "jp_eq", mhi.value_jpy, null);
  finalizeMix(mix);

  const mixTotal = MIX_CORE.reduce((s, b) => s + mix[b].value, 0);
  const mixCostKnown = MIX_CORE.reduce(
    (s, b) => s + (mix[b].cost ?? 0),
    0
  );
  const mixValueWithCost = MIX_CORE.reduce(
    (s, b) => s + (mix[b].cost != null ? mix[b].value : 0),
    0
  );
  const mixGainPct =
    mixCostKnown > 0 ? (mixValueWithCost - mixCostKnown) / mixCostKnown : null;

  const invIds = [
    "sbi_index",
    "bloomo",
    "akatsuki_bond",
    "mhi_stock",
    ...VARIABLE_INS,
  ];
  const invNow = invIds.reduce((s, id) => s + (latest.get(id)?.value_jpy ?? 0), 0);
  const invPrev = invIds.reduce((s, id) => s + (prev.get(id)?.value_jpy ?? 0), 0);
  const invDelta = invPrev > 0 ? invNow - invPrev : null;

  const sbiH = latestHoldings.get("sbi_index");
  const bloomoH = latestHoldings.get("bloomo");
  const akatsukiH = latestHoldings.get("akatsuki_bond");
  const sbiValue = sbiH?.value_jpy ?? latest.get("sbi_index")?.value_jpy ?? 0;
  const bloomoValue =
    bloomoH?.value_jpy ?? latest.get("bloomo")?.value_jpy ?? 0;
  const akatsukiValue =
    akatsukiH?.value_jpy ?? latest.get("akatsuki_bond")?.value_jpy ?? 0;
  const secCombined = sbiValue + bloomoValue;
  const sbiCost = (sbiH?.funds || []).reduce((s, f) => {
    const c = fundCost(f);
    return c != null ? s + c : s;
  }, 0);
  const sbiPnl = (sbiH?.funds || []).reduce((s, f) => s + yen(f.pnl_jpy), 0);

  const latestLiq = new Map<string, number>();
  for (const row of liqSnaps ?? []) {
    if (latestLiq.has(row.account_id)) continue;
    latestLiq.set(row.account_id, Number(row.balance_jpy) || 0);
  }
  const cashTotal = (liqAccounts ?? [])
    .filter((a) => a.kind === "bank" || a.kind === "cash")
    .reduce((s, a) => s + (latestLiq.get(a.id) ?? 0), 0);

  function fundRows(aid: string, funds: HoldingFund[]) {
    return funds.map((f, i) => {
      const value = num(f.value_jpy);
      const cost = fundCost(f);
      const pct = gainPct(value, cost);
      return (
        <tr key={`${aid}-${i}`}>
          <td>
            {f.code ? `${f.code} ` : ""}
            {f.name || "—"}
            <div className="meta">{MIX_LABEL[classifyHolding(f.name || "", f.code)]}</div>
          </td>
          <td className="num">{value != null ? fmtYen(value) : "—"}</td>
          <td className="num">{cost != null ? fmtYen(cost) : "—"}</td>
          <td className="num">{fmtPctSigned(pct)}</td>
        </tr>
      );
    });
  }

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
          <span className="lvl">ポートフォリオ</span>
          <strong>{fmtYen(mixTotal)}</strong>
        </header>
        <p className="meta">
          国内株式／海外株式／海外債券。保険の変額（アクサ・ソニー）は特別勘定の比率で按分。
          プルデンシャルは保障型のためこの3分類には入れていません。
          {invDelta != null
            ? ` 直近日差 ${fmtYenSigned(invDelta)}（変額保険＋証券＋持株＋あかつき）`
            : ""}
        </p>
        <table>
          <thead>
            <tr>
              <th>区分</th>
              <th className="num">評価</th>
              <th className="num">投下（分かる分）</th>
              <th className="num">増減率</th>
              <th className="num">構成</th>
            </tr>
          </thead>
          <tbody>
            {MIX_CORE.map((b) => {
              const row = mix[b];
              const share = mixTotal > 0 ? row.value / mixTotal : null;
              return (
                <tr key={b}>
                  <td>{MIX_LABEL[b]}</td>
                  <td className="num">{fmtYen(Math.round(row.value))}</td>
                  <td className="num">
                    {row.cost != null ? fmtYen(Math.round(row.cost)) : "一部のみ"}
                  </td>
                  <td className="num">{fmtPctSigned(row.gainPct)}</td>
                  <td className="num">{share != null ? fmtPct(share) : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {(mix.jp_bd.value > 0 || mix.cash.value > 0) && (
          <p className="meta" style={{ marginTop: 8 }}>
            参考: 国内債券 {fmtYen(Math.round(mix.jp_bd.value))}
            {mix.cash.value > 0
              ? ` · 保険の金融市場型 ${fmtYen(Math.round(mix.cash.value))}`
              : ""}
          </p>
        )}
        <p className="meta" style={{ marginTop: 6 }}>
          増減率が付くのは取得原価が取れた枠（主に SBI）。Bloomo・あかつき・保険は評価の内訳です。
          原価の分かる範囲の増減 {fmtPctSigned(mixGainPct)}。
        </p>
      </div>

      <div className="card">
        <header>
          <span className="lvl">生命保険（評価＋積立配分）</span>
          <strong>{fmtYen(insTotal)}</strong>
        </header>
        <p className="meta">
          右上は評価の合算。増減率は Zaim の払込累計に対する解約返戻（評価）。
          特別勘定の参考はアクサ（石川さん反映）。
          {alloc.snap_updated_at ? ` snap更新: ${alloc.snap_updated_at}` : ""}
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
              <th className="num">評価</th>
              <th className="num">払込累計</th>
              <th className="num">増減率</th>
              <th>配分</th>
              <th>対アクサ</th>
            </tr>
          </thead>
          <tbody>
            {insuranceRows.map((r) => {
              let cost: number | null = null;
              let valueForPct = r.value;
              let note: string | null = null;
              if (r.id === "axa_life") cost = paid.axa || null;
              else if (r.id === "sony_life" || r.id === "sony_life_chikage") {
                cost = paid.sony || null;
                valueForPct = sonyValue;
                note = "払込は真治・千景が同一費目。増減率は2契約合算";
              } else if (
                r.id === "prudential_life" ||
                r.id === "prudential_life_chikage"
              ) {
                cost = paid.prudential || null;
                valueForPct = pruValue;
                note =
                  "保障コスト込み。増減率は2契約合算（投資リターンではない）";
              }
              const pct = gainPct(valueForPct, cost);
              return (
                <tr key={r.id}>
                  <td>
                    {r.name}
                    {r.isRef ? <div className="meta">参考（正）</div> : null}
                    {note ? <div className="meta">{note}</div> : null}
                  </td>
                  <td className="num">
                    {r.value != null ? fmtYen(r.value) : "— 未取得"}
                    {r.snapAsOf ? (
                      <div className="meta">{r.snapAsOf}</div>
                    ) : null}
                  </td>
                  <td className="num">{cost != null ? fmtYen(cost) : "—"}</td>
                  <td className="num">{fmtPctSigned(pct)}</td>
                  <td>
                    {r.fundsText}
                    {r.asOf ? <div className="meta">{r.asOf}</div> : null}
                  </td>
                  <td>{r.vsAxa}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <table style={{ marginTop: 12 }}>
          <thead>
            <tr>
              <th>合算</th>
              <th className="num">評価</th>
              <th className="num">払込</th>
              <th className="num">増減率</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>ソニー（真治＋千景）</td>
              <td className="num">{fmtYen(sonyValue)}</td>
              <td className="num">{fmtYen(paid.sony)}</td>
              <td className="num">
                {fmtPctSigned(gainPct(sonyValue, paid.sony))}
              </td>
            </tr>
            <tr>
              <td>変額全体（アクサ＋ソニー）</td>
              <td className="num">{fmtYen(variableValue)}</td>
              <td className="num">{fmtYen(variablePaid)}</td>
              <td className="num">
                {fmtPctSigned(gainPct(variableValue, variablePaid))}
              </td>
            </tr>
            <tr>
              <td>プルデンシャル（保障型・2契約）</td>
              <td className="num">{fmtYen(pruValue)}</td>
              <td className="num">{fmtYen(paid.prudential)}</td>
              <td className="num">
                {fmtPctSigned(gainPct(pruValue, paid.prudential))}
              </td>
            </tr>
            <tr>
              <td>生命保険 全体</td>
              <td className="num">{fmtYen(insTotal)}</td>
              <td className="num">
                {fmtYen(paid.axa + paid.sony + paid.prudential)}
              </td>
              <td className="num">
                {fmtPctSigned(
                  gainPct(insTotal, paid.axa + paid.sony + paid.prudential)
                )}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="card">
        <header>
          <span className="lvl">保険借入（契約者貸付）</span>
          <strong>{fmtYen(loanTotal)}</strong>
        </header>
        <p className="meta">
          不動産購入の頭金枠把握用。返済戦略のため<strong>貸付利率（年%）</strong>
          も参考表示。利率は契約ごと — YAML／env で正本化（未記入は要確認）。
          {liabilityRates.updated_at
            ? ` rates更新: ${liabilityRates.updated_at}`
            : ""}
        </p>
        {sonyLoan > 0 ? (
          <p className="meta" style={{ marginTop: 6 }}>
            ソニー（真治）{fmtYen(sonyLoan)}
            は<strong>任意返済</strong>。毎月の定額引き落としはなく、Zaim
            にも返済行はありません。金利は年2.50%が元利に加算され、残高は据え置き（自動振替貸付は
            0円）。頭金枠として借りたまま、という状態です。
          </p>
        ) : null}
        <table>
          <thead>
            <tr>
              <th>口座</th>
              <th>借入残高</th>
              <th>利率</th>
              <th>日付</th>
            </tr>
          </thead>
          <tbody>
            {loanRows.map((r) => {
              const rate = liabilityRates.insurance[r.id];
              return (
                <tr key={r.id}>
                  <td>
                    {r.name}
                    {rate?.rate_note ? (
                      <div className="meta">{rate.rate_note}</div>
                    ) : null}
                  </td>
                  <td>{r.snap ? fmtYen(r.snap.value_jpy) : "— 未取得"}</td>
                  <td>
                    {fmtRatePct(rate?.rate_pct ?? null)}
                    {rate?.source ? (
                      <div className="meta">{rate.source}</div>
                    ) : null}
                  </td>
                  <td>{r.snap?.as_of ?? "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="card">
        <header>
          <span className="lvl">証券内訳（SBI ＋ Bloomo）</span>
          <strong>{fmtYen(secCombined)}</strong>
        </header>
        <p className="meta">
          右上は SBI {fmtYen(sbiValue)} ＋ Bloomo {fmtYen(bloomoValue)}。
          あかつき外国債券は下の債券枠（{fmtYen(akatsukiValue)}）。
          SBI＝Zaim 証券詳細／Bloomo＝マネーフォワード。
        </p>

        <details style={{ marginTop: 12 }} open>
          <summary>
            <strong>SBI インデックス</strong>{" "}
            <span className="meta">
              {fmtYen(sbiValue)} · 投下 {sbiCost ? fmtYen(sbiCost) : "—"} ·{" "}
              {fmtPctSigned(gainPct(sbiValue, sbiCost || null))}
              {sbiPnl ? ` · 損益 ${fmtYenSigned(sbiPnl)}` : ""} ·{" "}
              {sbiH?.as_of ?? "未取得"}
            </span>
          </summary>
          {!sbiH || sbiH.funds.length === 0 ? (
            <p className="meta">内訳未取得（週次で securities_holdings を実行）</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>銘柄</th>
                  <th className="num">評価</th>
                  <th className="num">投下</th>
                  <th className="num">増減率</th>
                </tr>
              </thead>
              <tbody>{fundRows("sbi_index", sbiH.funds)}</tbody>
            </table>
          )}
        </details>

        <details style={{ marginTop: 12 }} open>
          <summary>
            <strong>Bloomo</strong>{" "}
            <span className="meta">
              {fmtYen(bloomoValue)} · 取得原価はマネーフォワード未取得 ·{" "}
              {bloomoH?.as_of ?? "未取得"}
            </span>
          </summary>
          {!bloomoH || bloomoH.funds.length === 0 ? (
            <p className="meta">内訳未取得</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>銘柄</th>
                  <th className="num">評価</th>
                  <th className="num">投下</th>
                  <th className="num">増減率</th>
                </tr>
              </thead>
              <tbody>{fundRows("bloomo", bloomoH.funds)}</tbody>
            </table>
          )}
        </details>

        <details style={{ marginTop: 12 }} open>
          <summary>
            <strong>あかつき（外国債券）</strong>{" "}
            <span className="meta">
              {fmtYen(akatsukiValue)} · 債券1銘柄枠 ·{" "}
              {akatsukiH?.as_of ?? akatsukiSnap?.as_of ?? "未取得"}
            </span>
          </summary>
          <table>
            <thead>
              <tr>
                <th>銘柄</th>
                <th className="num">評価</th>
                <th className="num">投下</th>
                <th className="num">増減率</th>
              </tr>
            </thead>
            <tbody>
              {fundRows("akatsuki_bond", akatsukiH?.funds || [])}
            </tbody>
          </table>
          <p className="meta">
            週次スクレイプの保有資産評価。取得原価はサイトの評価損益列が取れ次第、増減率を付けます。
          </p>
        </details>
      </div>

      <div className="card notice">
        <header>
          <span className="lvl">Jarvis（PB）</span>
          <strong>寝かせて増やす前提の見立て</strong>
        </header>
        <p>
          『お金は寝かせて増やしなさい』どおり、<strong>コアは低コストの全世界（または先進国）株式インデックスを持ち続ける</strong>のが本線です。テーマ株の当てに時間を使うより、入金と年1回のリバランスで十分です。
        </p>
        <p className="meta" style={{ marginTop: 8 }}>
          いまの形: 海外株式（SBI 先進国・新興国＋Bloomo の米国ETF）が厚く、あかつき外国債券が約{" "}
          {mixTotal > 0 ? fmtPctSigned(mix.ex_bd.value / mixTotal) : "—"}
          。国内株式は日本株インデックス・持株・Bloomo の EWJ 程度。Bloomo
          の個別（GOOGL 等）とテーマETFは「動的スリーブ」として小さく置く、という整理が本に近いです。
        </p>
        <p>
          <strong>1. 世界テーマにいくら・何を</strong>
          …2026年の話題は AI／半導体、防衛、米株集中の見直しです。ただしコアをテーマに置き換えない。手元現金から新たに個別を買う必要は薄く、
          <strong>追加は SBI の先進国（または全世界）へ</strong>
          。テーマを触るなら Bloomo の動的側（いまの IXN・GOOGL など）の範囲に留め、枠の目安は金融資産の 5〜10%（Bloomo 全体でも約{" "}
          {fmtYen(bloomoValue)}）です。
        </p>
        <p>
          <strong>2. 現金と契約者貸付で今やること</strong>
          …銀行＋財布は約 {fmtYen(cashTotal)}
          。ソニー貸付は {fmtYen(sonyLoan)}・年2.50%・任意返済で、定額引き落としはありません。変額口座の期待リターンが金利を上回る前提なら、
          <strong>現金を空にして全額返済する必要はない</strong>
          （不動産のバッファと生活防衛資金を残す）。余った現金の使い道は①生活＋物件の半年〜1年分を確保 →
          ②残りをインデックスへ入金、が本に沿います。すららネットの含み損は個別株の典型で、コアの成績と混ぜて判断しない。
        </p>
        <p className="meta">
          プルデンシャルの払込対評価が大幅マイナスに見えるのは、保障コストが払込に含まれるためです。解約の判断材料にはしません。
        </p>
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
