import Shell from "@/components/Shell";
import MoneyOpStatusActions from "@/components/MoneyOpStatusActions";
import MoneyOpRailsPanel from "@/components/MoneyOpRailsPanel";
import NewMoneyOpForm from "@/components/NewMoneyOpForm";
import CardSettlementBufferForm from "@/components/CardSettlementBufferForm";
import { createClient } from "@/lib/supabase/server";
import { fmtYen } from "@/lib/format";
import {
  FUND_MOVE_UX,
  SMBC_SETTLEMENT_ACCOUNT_ID,
  SMBC_SETTLEMENT_ACCOUNT_LABEL,
} from "@/lib/cardSettlementBuffer";

export const dynamic = "force-dynamic";

export default async function MoneyOpsPage({
  searchParams,
}: {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = (await searchParams) || {};
  const dueParam = typeof sp.due === "string" ? sp.due : "";
  const needRaw = typeof sp.need === "string" ? sp.need : "";
  const needParam = needRaw ? Number(needRaw) : null;

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const [{ data: ops }, { data: liqSnaps }, { data: liqAccounts }, { data: debitMeta }] =
    await Promise.all([
      supabase
        .from("kurashift_money_ops")
        .select(
          "id, title, kind, rationale, from_account, to_account, amount_jpy, status, assist_payload, created_at"
        )
        .order("created_at", { ascending: false })
        .limit(40),
      supabase
        .from("liquidity_snapshots")
        .select("account_id, as_of, balance_jpy")
        .order("as_of", { ascending: false })
        .limit(80),
      supabase
        .from("liquidity_accounts")
        .select("id, name, kind")
        .eq("active", true),
      supabase
        .from("sync_meta")
        .select("value")
        .eq("key", "card_debit_watch_summary")
        .maybeSingle(),
    ]);

  let prefillDue = dueParam;
  let prefillNeed =
    needParam != null && Number.isFinite(needParam) ? needParam : null;
  if ((!prefillDue || prefillNeed == null) && debitMeta?.value) {
    try {
      const brief = JSON.parse(debitMeta.value) as {
        olive_infinite?: { due_date?: string; amount_jpy?: number | null };
        top_alert?: { due_date?: string; amount_jpy?: number | null };
      };
      const olive = brief.olive_infinite || {};
      const top = brief.top_alert || {};
      if (!prefillDue) {
        prefillDue = String(top.due_date || olive.due_date || "");
      }
      if (prefillNeed == null) {
        const n = top.amount_jpy ?? olive.amount_jpy;
        if (typeof n === "number" && Number.isFinite(n)) prefillNeed = n;
      }
    } catch {
      /* ignore */
    }
  }

  const accountById = new Map(
    (liqAccounts ?? []).map((a) => [a.id, { name: a.name, kind: a.kind }])
  );
  const latest = new Map<string, { as_of: string; balance_jpy: number }>();
  for (const row of liqSnaps ?? []) {
    if (!latest.has(row.account_id)) {
      latest.set(row.account_id, {
        as_of: row.as_of,
        balance_jpy: Number(row.balance_jpy),
      });
    }
  }

  // 引落口座は smbc_kariya 1本（Oliveカード口座などを足し込まない）
  const smbcSnap = latest.get(SMBC_SETTLEMENT_ACCOUNT_ID);
  const smbcBalance =
    smbcSnap != null && Number.isFinite(smbcSnap.balance_jpy)
      ? smbcSnap.balance_jpy
      : null;

  // 銀行＋現金のみ（カード・電子マネーは寄せ対象外）
  let liquidityTotal = 0;
  let hasLiquidity = false;
  for (const [id, snap] of latest) {
    const meta = accountById.get(id);
    const kind = meta?.kind || "";
    if (kind === "bank" || kind === "cash") {
      liquidityTotal += snap.balance_jpy;
      hasLiquidity = true;
    }
  }
  const fundingGap =
    prefillNeed != null && smbcBalance != null ? Math.max(prefillNeed - smbcBalance, 0) : 0;
  const moneyGateLabel =
    fundingGap > 0
      ? "要寄せ / 要調達"
      : prefillNeed != null && smbcBalance != null && smbcBalance < prefillNeed * 1.2
        ? "注意"
        : prefillNeed != null
          ? "余裕あり"
          : "確認待ち";

  return (
    <Shell active="/money-ops" email={user?.email ?? null}>
      <h1>資金移動オペ</h1>
      <p className="sub">
        draft → consulting → approved → executing → done。承認＝計画合意のみ（実弾は動かない）。
        実行はレールごと: {FUND_MOVE_UX.steps.map((s) => s.label).join(" → ")}。
        あなたは「プラン承認・最終画面確認・OTP＋実行ボタン」だけ。終わった送金用 Chrome は Jarvis が閉じます。
      </p>

      <div className="card" style={{ marginTop: 12 }}>
        <header>
          <span className="lvl">ゲート</span>
          <strong>今月のキャッシュゲート: {moneyGateLabel}</strong>
        </header>
        <p className="meta" style={{ marginTop: 6 }}>
          引落口座 {SMBC_SETTLEMENT_ACCOUNT_LABEL} {fmtYen(smbcBalance)} / 手元流動性{" "}
          {fmtYen(hasLiquidity ? liquidityTotal : null)}
          {prefillNeed != null ? ` / 今回必要額 ${fmtYen(prefillNeed)}` : ""}
        </p>
        <p className="meta" style={{ marginTop: 6 }}>
          {fundingGap > 0
            ? `まず寄せの候補整理。現時点の不足は ${fmtYen(fundingGap)}。`
            : "当月の引落事故防止を優先し、その後に投資・返済判断へ進みます。"}
        </p>
      </div>

      <CardSettlementBufferForm
        smbcBalanceYen={smbcBalance}
        smbcAccountLabel={SMBC_SETTLEMENT_ACCOUNT_LABEL}
        liquidityTotalYen={hasLiquidity ? liquidityTotal : null}
        initialDueDate={prefillDue || null}
        initialNeedYen={prefillNeed}
      />

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
                const payload =
                  o.assist_payload && typeof o.assist_payload === "object"
                    ? (o.assist_payload as Record<string, unknown>)
                    : null;
                const steps =
                  payload && Array.isArray(payload.steps)
                    ? (payload.steps as string[])
                    : [];
                const due =
                  payload && typeof payload.due_date === "string"
                    ? payload.due_date
                    : null;
                const rails =
                  payload && Array.isArray(payload.rails)
                    ? (payload.rails as Array<{
                        id?: string;
                        label?: string;
                        amount_jpy?: number;
                        status?: string;
                        otp_channel?: string;
                        manual_iphone?: string;
                        evidence?: string | null;
                        last_error?: string | null;
                        note?: string | null;
                        remind_at?: string | null;
                      }>)
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
                        {due ? ` · 引落日 ${due}` : ""}
                      </div>
                      {rails.length > 0 ? (
                        <MoneyOpRailsPanel
                          opId={o.id}
                          rails={rails}
                          showUx={
                            o.status === "approved" ||
                            o.status === "executing" ||
                            o.status === "consulting"
                          }
                        />
                      ) : null}
                      {o.status === "approved" ||
                      o.status === "executing" ||
                      o.status === "consulting" ? (
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
                      <MoneyOpStatusActions
                        id={o.id}
                        status={o.status}
                        kind={o.kind}
                      />
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
