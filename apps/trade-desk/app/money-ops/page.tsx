import Shell from "@/components/Shell";
import MoneyOpStatusActions from "@/components/MoneyOpStatusActions";
import NewMoneyOpForm from "@/components/NewMoneyOpForm";
import { createClient } from "@/lib/supabase/server";
import { fmtYen } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function MoneyOpsPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { data: ops } = await supabase
    .from("kurashift_money_ops")
    .select(
      "id, title, kind, rationale, from_account, to_account, amount_jpy, status, assist_payload, created_at"
    )
    .order("created_at", { ascending: false })
    .limit(40);

  return (
    <Shell active="/money-ops" email={user?.email ?? null}>
      <h1>資金移動オペ</h1>
      <p className="sub">
        draft → consulting → approved → executing → done。承認前に実弾は動きません。
        銀行・証券の振込確定と保険配分変更の自動実行は対象外（手順アシストまで）。
      </p>

      <NewMoneyOpForm />

      <div className="card">
        <header>
          <span className="lvl">Money ops</span>
          <strong>一覧</strong>
        </header>
        <table>
          <thead>
            <tr>
              <th>状態</th>
              <th>内容</th>
              <th>金額</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {(ops ?? []).length === 0 ? (
              <tr>
                <td colSpan={4} className="meta">
                  まだオペがありません。
                </td>
              </tr>
            ) : (
              (ops ?? []).map((o) => {
                const steps =
                  o.assist_payload &&
                  typeof o.assist_payload === "object" &&
                  Array.isArray(
                    (o.assist_payload as { steps?: string[] }).steps
                  )
                    ? (o.assist_payload as { steps: string[] }).steps
                    : [];
                return (
                  <tr key={o.id}>
                    <td>
                      <strong>{o.status}</strong>
                      <div className="meta">{o.kind}</div>
                    </td>
                    <td>
                      <strong>{o.title}</strong>
                      <div className="meta">{o.rationale}</div>
                      <div className="meta">
                        {o.from_account ?? "—"} → {o.to_account ?? "—"}
                      </div>
                      {o.status === "approved" || o.status === "executing" ? (
                        <ul className="meta" style={{ marginTop: 6 }}>
                          {steps.map((s) => (
                            <li key={s}>{s}</li>
                          ))}
                        </ul>
                      ) : null}
                    </td>
                    <td>
                      {o.amount_jpy != null
                        ? fmtYen(Number(o.amount_jpy))
                        : "—"}
                    </td>
                    <td>
                      <MoneyOpStatusActions id={o.id} status={o.status} />
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}
