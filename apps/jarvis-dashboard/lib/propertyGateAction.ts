import { createHmac, timingSafeEqual } from "crypto";
import { NextResponse } from "next/server";
import { createServiceClient } from "@/lib/supabase/admin";

export type GateAction = "yes" | "no";

export function htmlPage(title: string, body: string, ok: boolean) {
  const color = ok ? "#065f46" : "#991b1b";
  return new NextResponse(
    `<!doctype html><html lang="ja"><meta charset="utf-8"/>
<title>${title}</title>
<body style="font-family:system-ui;padding:2rem;max-width:36rem;color:${color}">
<h1 style="font-size:1.25rem">${title}</h1>
<pre style="white-space:pre-wrap;background:#f3f4f6;padding:1rem;border-radius:8px;color:#111">${body}</pre>
<p style="color:#6b7280;font-size:0.875rem">このタブは閉じて大丈夫です。結果は Slack #consult にも出ます。</p>
</body></html>`,
    {
      status: ok ? 200 : 400,
      headers: { "Content-Type": "text/html; charset=utf-8" },
    },
  );
}

export function tokenOk(token: string | null | undefined): boolean {
  const expected = (process.env.PROPERTY_GATE_ACTION_TOKEN || "").trim();
  if (!expected) return false;
  const got = (token || "").trim();
  if (!got || got.length !== expected.length) return false;
  try {
    return timingSafeEqual(Buffer.from(got), Buffer.from(expected));
  } catch {
    return false;
  }
}

/** 短縮 URL 用 HMAC（先頭10桁）。秘密は PROPERTY_GATE_ACTION_TOKEN。 */
export function actionSig(dealId: string, action: GateAction): string {
  const secret = (process.env.PROPERTY_GATE_ACTION_TOKEN || "").trim();
  return createHmac("sha256", secret)
    .update(`${dealId}:${action}`, "utf8")
    .digest("hex")
    .slice(0, 10);
}

export function sigOk(
  dealId: string,
  action: GateAction,
  sig: string | null | undefined,
): boolean {
  const expected = actionSig(dealId, action);
  const got = (sig || "").trim().toLowerCase();
  if (!got || got.length !== expected.length) return false;
  try {
    return timingSafeEqual(Buffer.from(got), Buffer.from(expected));
  } catch {
    return false;
  }
}

export function parseAction(raw: string | null | undefined): GateAction | null {
  const a = (raw || "").trim().toLowerCase();
  if (a === "yes" || a === "y" || a === "進めて") return "yes";
  if (a === "no" || a === "n" || a === "見送り") return "no";
  return null;
}

function esc(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function cleanListingUrl(raw: string): string {
  let s = (raw || "").trim().split("（")[0].split("(")[0].trim();
  try {
    const u = new URL(s);
    if (
      (u.hostname === "www.google.com" || u.hostname === "google.com") &&
      u.pathname === "/url"
    ) {
      const q = u.searchParams.get("q") || u.searchParams.get("url");
      if (q) return q.trim();
    }
  } catch {
    /* ignore */
  }
  return s;
}

type DealRow = {
  id: string;
  title?: string | null;
  price_man?: number | null;
  match_score?: number | null;
  area?: string | null;
  summary_json?: Record<string, unknown> | null;
};

/** ログイン不要の判断材料表（Slack カードと同項目）。 */
export function judgmentDetailHtml(deal: DealRow): string {
  const sj =
    deal.summary_json && typeof deal.summary_json === "object"
      ? deal.summary_json
      : {};
  const g =
    sj.grok && typeof sj.grok === "object"
      ? (sj.grok as Record<string, unknown>)
      : {};
  const pick = (...keys: string[]) => {
    for (const k of keys) {
      const v = g[k] ?? sj[k];
      if (v !== undefined && v !== null && String(v).trim()) return String(v).trim();
    }
    return "—";
  };
  let price = "—";
  const pm = deal.price_man ?? g.price_man;
  if (pm !== undefined && pm !== null && pm !== "") {
    const n = Number(pm);
    price = Number.isFinite(n) ? `${Math.round(n)}万` : `${pm}万`;
  }
  const url = cleanListingUrl(pick("url", "listing_url", "inquiry_url"));
  const locRaw = pick("location");
  const loc = locRaw !== "—" ? locRaw : String(deal.area || "—");

  const num = (s: string): number | null => {
    const m = String(s).match(/-?\d[\d,]*(?:\.\d+)?/);
    if (!m) return null;
    const n = Number(m[0].replace(/,/g, ""));
    return Number.isFinite(n) ? n : null;
  };
  const priceMan = num(price);
  const landValMan = num(pick("land_appraisal_man"));
  const ratioNum = num(pick("land100_ratio", "land_ratio", "land100"));
  const landRatioPct =
    landValMan != null && priceMan
      ? Math.round((landValMan / priceMan) * 100)
      : ratioNum == null
        ? null
        : Math.round(ratioNum < 10 ? ratioNum * 100 : ratioNum);
  const landValDerived =
    landValMan ??
    (landRatioPct != null && priceMan ? (landRatioPct / 100) * priceMan : null);
  const landValText =
    landValDerived != null
      ? `約${Math.round(landValDerived).toLocaleString()}万`
      : "—";
  const landRatioText =
    landRatioPct != null ? `${landRatioPct}%（＝土地値÷価格）` : "—";

  const rows: [string, string][] = [
    ["所在", loc],
    ["価格", price],
    ["土地値", landValText],
    ["土地値率", landRatioText],
    ["土地", pick("land_area")],
    ["路線価手法", pick("land_method")],
    ["建物", pick("building")],
    ["ハザード総合", pick("hazard_eval")],
    ["洪水", pick("hazard_flood")],
    ["高潮", pick("hazard_storm_surge")],
    ["急傾斜", pick("hazard_landslide")],
    ["内水", pick("hazard_inland")],
    ["聞く/保留", pick("listen_value")],
    ["問合せ経路", pick("inquiry_action")],
    ["score", deal.match_score != null ? String(deal.match_score) : "—"],
  ];
  if (url && url !== "—") rows.push(["掲載URL", url]);

  const tr = rows
    .map(
      ([k, v]) =>
        `<tr><th>${esc(k)}</th><td>${
          k === "掲載URL" && v.startsWith("http")
            ? `<a href="${esc(v)}" target="_blank" rel="noopener">${esc(v)}</a>`
            : esc(v)
        }</td></tr>`,
    )
    .join("\n");

  const yes = `/api/g/y/${deal.id}?s=${actionSig(deal.id, "yes")}`;
  const no = `/api/g/n/${deal.id}?s=${actionSig(deal.id, "no")}`;
  const title = esc(String(deal.title || "物件").slice(0, 100));

  return `<!doctype html><html lang="ja"><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>判断材料 — ${title}</title>
<style>
  body{font-family:system-ui,-apple-system,sans-serif;margin:0;padding:1.25rem;background:#f8fafc;color:#0f172a}
  .wrap{max-width:40rem;margin:0 auto;background:#fff;border-radius:12px;padding:1.25rem 1.25rem 1.5rem;box-shadow:0 1px 3px rgba(0,0,0,.08)}
  h1{font-size:1.1rem;margin:0 0 .75rem;line-height:1.4}
  table{width:100%;border-collapse:collapse;font-size:.9rem}
  th,td{border-bottom:1px solid #e2e8f0;padding:.55rem .4rem;vertical-align:top;text-align:left}
  th{width:7.5rem;color:#64748b;font-weight:600;white-space:nowrap}
  td{word-break:break-word}
  .actions{display:flex;gap:.75rem;margin-top:1.25rem;flex-wrap:wrap}
  .actions a{display:inline-block;padding:.7rem 1.1rem;border-radius:8px;text-decoration:none;font-weight:600;font-size:.95rem}
  .yes{background:#059669;color:#fff}
  .no{background:#e2e8f0;color:#334155}
  .note{margin-top:1rem;font-size:.8rem;color:#64748b}
</style>
<body><div class="wrap">
<h1>${title}</h1>
<table><tbody>${tr}</tbody></table>
<div class="actions">
  <a class="yes" href="${yes}">問合せする（Yes）</a>
  <a class="no" href="${no}">見送り（No）</a>
</div>
<p class="note">ログイン不要の判断ページです。KURASHIFT本体の詳細画面とは別です。</p>
</div></body></html>`;
}

export async function fetchDealForJudgment(
  dealId: string,
): Promise<DealRow | null> {
  const sb = createServiceClient();
  if (!sb) return null;
  const { data, error } = await sb
    .from("kurashift_re_deals")
    .select("id, title, price_man, match_score, area, summary_json")
    .eq("id", dealId)
    .maybeSingle();
  if (error || !data) return null;
  return data as DealRow;
}

export async function applyGate(
  dealId: string,
  action: GateAction,
  source: string,
): Promise<{ ok: boolean; message: string; job_id?: string }> {
  const sb = createServiceClient();
  if (!sb) {
    return { ok: false, message: "Service Role 未設定" };
  }

  const { data: row, error } = await sb
    .from("kurashift_re_deals")
    .select("id, title, inquiry_status, summary_json, status")
    .eq("id", dealId)
    .maybeSingle();
  if (error || !row) {
    return { ok: false, message: error?.message || "deal not found" };
  }

  const sj =
    row.summary_json && typeof row.summary_json === "object"
      ? ({ ...(row.summary_json as Record<string, unknown>) } as Record<
          string,
          unknown
        >)
      : {};
  const prevGate =
    sj.property_gate && typeof sj.property_gate === "object"
      ? (sj.property_gate as Record<string, unknown>)
      : {};
  const prevDecision = String(prevGate.decision || "");
  const inq = String(row.inquiry_status || sj.inquiry_status || "none");
  const now = new Date().toISOString();
  const title = String(row.title || "").slice(0, 60);
  const alreadySent =
    Boolean(sj.inquiry_sent_at) ||
    String(prevGate.send_result || "").includes("sent") ||
    Boolean(prevGate.gmail_id);

  if (action === "no") {
    if (prevDecision === "no") {
      return { ok: true, message: `既に見送り済: ${title}` };
    }
    sj.inquiry_status = "none";
    sj.property_gate = { ...prevGate, decision: "no", at: now, source };
    sj.auto_pass_reason = sj.auto_pass_reason || "property_gate_no";
    await sb
      .from("kurashift_re_deals")
      .update({
        status: "passed",
        inquiry_status: "none",
        summary_json: sj,
        updated_at: now,
      })
      .eq("id", dealId);
    return { ok: true, message: `見送りにしました: ${title}` };
  }

  // yes
  if (
    prevDecision === "yes" ||
    prevDecision === "sent" ||
    inq === "sending" ||
    inq === "awaiting_reply" ||
    inq === "has_reply" ||
    alreadySent
  ) {
    return {
      ok: true,
      message: `既に進行中/送信済 (inq=${inq}): ${title}`,
    };
  }

  const idempotencyKey = `${dealId}:first_inquiry`;
  const { data: existingJobs } = await sb
    .from("kurashift_jobs")
    .select("id, status, payload")
    .eq("job_type", "re_deal_inquiry_send")
    .in("status", ["queued", "running", "succeeded"])
    .order("created_at", { ascending: false })
    .limit(40);

  const dup = (existingJobs || []).find((j) => {
    const p =
      j.payload && typeof j.payload === "object"
        ? (j.payload as Record<string, unknown>)
        : {};
    return p.deal_id === dealId || p.idempotency_key === idempotencyKey;
  });
  if (dup) {
    return {
      ok: true,
      message: `送信ジョブ既存 (${dup.status}): ${title}`,
      job_id: String(dup.id),
    };
  }

  // handoff 誤ラベル修復
  if (inq === "awaiting_grok" && sj.awaiting_kurashift_first_inquiry) {
    sj.inquiry_status = "awaiting_first_inquiry";
  }

  sj.inquiry_status = "sending";
  sj.property_gate = { ...prevGate, decision: "yes", at: now, source };
  await sb
    .from("kurashift_re_deals")
    .update({
      inquiry_status: "sending",
      summary_json: sj,
      updated_at: now,
    })
    .eq("id", dealId);

  const { data: job, error: jobErr } = await sb
    .from("kurashift_jobs")
    .insert({
      job_type: "re_deal_inquiry_send",
      title: `第一問合せ(Slackゲート): ${title}`,
      status: "queued",
      payload: {
        deal_id: dealId,
        ui_confirmed: true,
        ui_confirmed_at: now,
        slack_gate_yes: true,
        confirm_source: source,
        idempotency_key: idempotencyKey,
      },
      created_by: "slack_consult_action",
    })
    .select("id")
    .single();

  if (jobErr) {
    return { ok: false, message: jobErr.message };
  }
  return {
    ok: true,
    message: `問合せ送信をキューしました: ${title}`,
    job_id: job?.id ? String(job.id) : undefined,
  };
}
