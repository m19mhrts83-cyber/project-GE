import Shell from "@/components/Shell";
import RealEstateLaneNav from "@/components/RealEstateLaneNav";
import { createClient } from "@/lib/supabase/server";
import FinancePackClient from "./FinancePackClient";

export const dynamic = "force-dynamic";

function fmtYen(n: number): string {
  return new Intl.NumberFormat("ja-JP", {
    style: "currency",
    currency: "JPY",
    maximumFractionDigits: 0,
  }).format(n);
}

export default async function FinancePackPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { data: loans } = await supabase
    .from("kurashift_loan_tracker_loans")
    .select("balance_jpy, name");

  const total =
    loans?.reduce((a, l) => a + (Number(l.balance_jpy) || 0), 0) ?? 0;
  const loanSummary =
    loans && loans.length > 0
      ? `${loans.length}本 · 残高合計 ${fmtYen(total)}`
      : "投影なし（sync 後に表示）";

  return (
    <Shell active="/realestate" email={user?.email ?? null}>
      <RealEstateLaneNav active="d" />
      <p className="page-kicker">③-D · 融資</p>
      <h1>融資提出パック</h1>
      <p className="sub">
        物件購入・運転資金・フリー・教育の書類チェック。個人／法人分離、マイナは共通。
        自動送信・自動アップロードはしません。
        {" · "}
        <a href="/realestate/lenders">銀行アプローチ先 →</a>
        {" · "}
        <a href="/realestate">不動産ハブ →</a>
        {" · "}
        <a href="/realestate/properties">物件マスタ →</a>
      </p>

      <FinancePackClient loanSummary={loanSummary} />

      <div className="card">
        <header>
          <span className="lvl">Docs</span>
          <strong>参照</strong>
        </header>
        <ul className="meta" style={{ paddingLeft: 18, marginTop: 8 }}>
          <li>
            <code>docs/KURASHIFT_融資提出パック.md</code>
          </li>
          <li>
            <code>config/kurashift_re_finance_doc_templates.yaml</code>
          </li>
          <li>
            OneDrive <code>240_融資/finance_packs/</code>・
            <code>243_カードローン書類/</code>
          </li>
        </ul>
      </div>
    </Shell>
  );
}
