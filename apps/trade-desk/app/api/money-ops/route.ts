import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";

const KINDS = new Set([
  "bank_transfer",
  "broker_transfer",
  "securities_cash",
  "insurance_alloc",
]);

export async function POST(req: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const body = await req.json().catch(() => ({}));
  const title = String(body.title || "").trim();
  const kind = String(body.kind || "bank_transfer");
  if (!title) {
    return NextResponse.json({ error: "title required" }, { status: 400 });
  }
  if (!KINDS.has(kind)) {
    return NextResponse.json({ error: "invalid kind" }, { status: 400 });
  }

  const amount =
    body.amount_jpy == null || body.amount_jpy === ""
      ? null
      : Number(body.amount_jpy);

  const { data, error } = await supabase
    .from("kurashift_money_ops")
    .insert({
      title,
      kind,
      rationale: String(body.rationale || ""),
      from_account: body.from_account ? String(body.from_account) : null,
      to_account: body.to_account ? String(body.to_account) : null,
      amount_jpy: Number.isFinite(amount as number) ? amount : null,
      status: "draft",
      assist_payload: {
        steps: [
          "承認後に手順アシストを確認",
          "銀行／証券の振込確定は手動（自動振込なし）",
          "保険配分変更はアシストのみ",
        ],
      },
    })
    .select("id, title, status, kind")
    .single();

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true, op: data });
}
