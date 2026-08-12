import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";

const ALLOWED: Record<string, string[]> = {
  draft: ["consulting", "approved", "closed"],
  consulting: ["draft", "approved", "closed"],
  approved: ["executing", "consulting", "closed"],
  executing: ["reviewed", "closed"],
  reviewed: ["closed"],
  closed: ["draft"],
};

function buildConsultBody(theme: {
  title: string;
  hypothesis?: string | null;
  amount_jpy?: number | string | null;
  duration_note?: string | null;
  funding_path?: string | null;
}): string {
  const lines = [
    `【テーマ】${theme.title}`,
    "",
    "【仮説・内容】",
    String(theme.hypothesis || "（未記入）"),
  ];
  if (theme.amount_jpy != null && theme.amount_jpy !== "") {
    lines.push("", `【金額目安】${theme.amount_jpy} 円`);
  }
  if (theme.duration_note) {
    lines.push(`【期間】${theme.duration_note}`);
  }
  if (theme.funding_path) {
    lines.push(`【資金経路】${theme.funding_path}`);
  }
  lines.push(
    "",
    "——",
    "相談メモ（Jarvis／自分）:",
    "（ここに判断材料・懸念・合意事項を追記）"
  );
  return lines.join("\n");
}

export async function PATCH(
  req: Request,
  ctx: { params: Promise<{ id: string }> }
) {
  const { id } = await ctx.params;
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const body = await req.json().catch(() => ({}));
  const next = String(body.status || "");
  const ensureOnly = Boolean(body.ensure_consultation) && !next;

  const { data: row, error: getErr } = await supabase
    .from("kurashift_themes")
    .select(
      "id, status, title, hypothesis, amount_jpy, duration_note, funding_path, payload, review_note, consultation_id"
    )
    .eq("id", id)
    .maybeSingle();
  if (getErr || !row) {
    return NextResponse.json(
      { error: getErr?.message || "not found" },
      { status: 404 }
    );
  }

  let consultationId = row.consultation_id as string | null;

  async function createConsultationIfNeeded(): Promise<string | null> {
    if (consultationId) return consultationId;
    const now = new Date().toISOString();
    const { data: cons, error: cErr } = await supabase
      .from("kurashift_consultations")
      .insert({
        title: `相談: ${row!.title}`,
        body: buildConsultBody(row!),
        lane: "theme",
        status: "open",
        metadata: { theme_id: id, source: "theme_to_consulting" },
        updated_at: now,
      })
      .select("id")
      .single();
    if (cErr || !cons) {
      throw new Error(cErr?.message || "consultation create failed");
    }
    return cons.id as string;
  }

  if (ensureOnly) {
    try {
      consultationId = await createConsultationIfNeeded();
    } catch (e) {
      return NextResponse.json(
        { error: e instanceof Error ? e.message : "failed" },
        { status: 500 }
      );
    }
    const { data, error } = await supabase
      .from("kurashift_themes")
      .update({
        consultation_id: consultationId,
        updated_at: new Date().toISOString(),
      })
      .eq("id", id)
      .select("id, title, status, consultation_id")
      .single();
    if (error) {
      return NextResponse.json({ error: error.message }, { status: 500 });
    }
    return NextResponse.json({
      ok: true,
      theme: data,
      consultation_id: consultationId,
    });
  }

  if (!next) {
    return NextResponse.json({ error: "status required" }, { status: 400 });
  }

  const allowed = ALLOWED[row.status] || [];
  if (!allowed.includes(next)) {
    return NextResponse.json(
      { error: `遷移不可: ${row.status} → ${next}`, allowed },
      { status: 400 }
    );
  }

  const patch: Record<string, unknown> = {
    status: next,
    updated_at: new Date().toISOString(),
  };
  if (body.review_note != null) {
    patch.review_note = String(body.review_note);
  }

  // 相談中へ: 相談レコードが無ければテーマ内容から作成しリンク
  if (next === "consulting" && !consultationId) {
    try {
      consultationId = await createConsultationIfNeeded();
    } catch (e) {
      return NextResponse.json(
        { error: e instanceof Error ? e.message : "failed" },
        { status: 500 }
      );
    }
    patch.consultation_id = consultationId;
  }

  if (next === "approved") {
    const prev =
      row.payload && typeof row.payload === "object" ? row.payload : {};
    patch.payload = {
      ...prev,
      approved_at: new Date().toISOString(),
      approved_by: user.email ?? user.id,
      live: false,
      approved_via: body.approved_via || "theme_list",
    };

    // 相談から承認したとき: 相談を decided に（任意 decision）
    if (consultationId) {
      const decision =
        body.decision != null
          ? String(body.decision)
          : "テーマ承認（相談内容を確認のうえ）";
      await supabase
        .from("kurashift_consultations")
        .update({
          status: "decided",
          decision,
          updated_at: new Date().toISOString(),
        })
        .eq("id", consultationId);
    }
  }

  const { data, error } = await supabase
    .from("kurashift_themes")
    .update(patch)
    .eq("id", id)
    .select("id, title, status, review_note, consultation_id")
    .single();
  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  return NextResponse.json({
    ok: true,
    theme: data,
    consultation_id: consultationId,
  });
}
