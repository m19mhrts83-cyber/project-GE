import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";
import type { CashflowColumnKey } from "@/lib/mqCashflowColumns";
import {
  buildLearnRuleFromTxn,
  type CashflowClassifyRuleRow,
} from "@/lib/mqCashflowClassify";

const TXN_COLS =
  "id,category,subcategory,entity,kind,txn_date,income_jpy,expense_jpy";

export async function PATCH(req: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const body = await req.json().catch(() => ({}));
  const txnId = Number(body.txnId);
  const businessLine = String(body.businessLine || "realestate");
  const cashflowColumn = String(body.cashflowColumn || "") as CashflowColumnKey;
  const learnRule = body.learnRule !== false;
  const note = body.note ? String(body.note).slice(0, 500) : null;

  if (!Number.isFinite(txnId) || !cashflowColumn) {
    return NextResponse.json(
      { error: "txnId and cashflowColumn required" },
      { status: 400 }
    );
  }

  const { data: txn, error: txnErr } = await supabase
    .from("kurashift_finance_transactions")
    .select(TXN_COLS)
    .eq("id", txnId)
    .maybeSingle();

  if (txnErr) {
    return NextResponse.json({ error: txnErr.message }, { status: 500 });
  }
  if (!txn) {
    return NextResponse.json({ error: "txn not found" }, { status: 404 });
  }

  const { data: override, error: ovErr } = await supabase
    .from("kurashift_mq_cashflow_txn_overrides")
    .upsert(
      {
        txn_id: txnId,
        business_line: businessLine,
        cashflow_column: cashflowColumn,
        note,
        created_by: user.id,
        updated_at: new Date().toISOString(),
      },
      { onConflict: "txn_id,business_line" }
    )
    .select("*")
    .single();

  if (ovErr) {
    return NextResponse.json({ error: ovErr.message }, { status: 500 });
  }

  let rule: CashflowClassifyRuleRow | null = null;
  if (learnRule) {
    const payload = buildLearnRuleFromTxn(
      txn,
      businessLine,
      cashflowColumn,
      txnId
    );
    const { data: ruleRow, error: ruleErr } = await supabase
      .from("kurashift_mq_cashflow_classify_rules")
      .upsert(
        {
          ...payload,
          source_txn_id: txnId,
          created_by: user.id,
          updated_at: new Date().toISOString(),
        },
        {
          onConflict: "business_line,entity_match,category_match,subcategory_match",
        }
      )
      .select("*")
      .single();
    if (ruleErr) {
      return NextResponse.json({ error: ruleErr.message }, { status: 500 });
    }
    rule = ruleRow as CashflowClassifyRuleRow;
  }

  return NextResponse.json({ ok: true, override, rule, learnRule });
}

export async function DELETE(req: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const url = new URL(req.url);
  const txnId = Number(url.searchParams.get("txnId"));
  const businessLine = url.searchParams.get("businessLine") || "realestate";

  if (!Number.isFinite(txnId)) {
    return NextResponse.json({ error: "txnId required" }, { status: 400 });
  }

  const { error } = await supabase
    .from("kurashift_mq_cashflow_txn_overrides")
    .delete()
    .eq("txn_id", txnId)
    .eq("business_line", businessLine);

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json({ ok: true });
}
