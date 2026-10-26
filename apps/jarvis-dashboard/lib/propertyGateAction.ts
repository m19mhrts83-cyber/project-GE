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
  yield_pct?: number | null;
  structure?: string | null;
  match_score?: number | null;
  area?: string | null;
  summary_json?: Record<string, unknown> | null;
};

export type DealEvent = {
  event_type?: string | null;
  actor?: string | null;
  summary?: string | null;
  occurred_at?: string | null;
};

const EVENT_LABEL: Record<string, string> = {
  created: "登録",
  status_change: "状態変更",
  inquiry_sent: "問合せ送信",
  inquiry_reply: "返信受信",
  grok_applied: "Grok反映",
  grok_handoff_sent: "KURASHIFTへ引継ぎ",
  grok_handoff_ready: "引継ぎ準備",
  review_confirm: "確認",
  review_pass: "見送り",
  note: "メモ",
};

function fmtWhen(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso).slice(0, 16);
  return d.toLocaleString("ja-JP", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Tokyo",
  });
}

/** ログイン不要の判断材料表（Slack カードと同項目）。 */
export function judgmentDetailHtml(deal: DealRow, events: DealEvent[] = []): string {
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
  const appraisalRaw = pick("land_appraisal_man");
  const ratioRaw = pick("land100_ratio", "land_ratio", "land100");
  // 複数シナリオ「1,494（91E）／1,805（110E）」をそのまま見せる
  const landValText =
    appraisalRaw !== "—"
      ? appraisalRaw
      : (() => {
          const landValMan = num(appraisalRaw);
          const ratioNum = num(ratioRaw);
          const landRatioPct =
            landValMan != null && priceMan
              ? Math.round((landValMan / priceMan) * 100)
              : ratioNum == null
                ? null
                : Math.round(ratioNum < 10 ? ratioNum * 100 : ratioNum);
          const landValDerived =
            landValMan ??
            (landRatioPct != null && priceMan
              ? (landRatioPct / 100) * priceMan
              : null);
          return landValDerived != null
            ? `約${Math.round(landValDerived).toLocaleString()}万`
            : "—";
        })();
  const landRatioText =
    ratioRaw !== "—"
      ? `${ratioRaw}（＝土地値÷価格）`
      : (() => {
          const landValMan = num(appraisalRaw);
          const ratioNum = num(ratioRaw);
          const landRatioPct =
            landValMan != null && priceMan
              ? Math.round((landValMan / priceMan) * 100)
              : ratioNum == null
                ? null
                : Math.round(ratioNum < 10 ? ratioNum * 100 : ratioNum);
          return landRatioPct != null
            ? `${landRatioPct}%（＝土地値÷価格）`
            : "—";
        })();

  const isAp = /AP|アパート|一棟|マンション|収益/i.test(
    `${deal.structure || ""} ${deal.title || ""}`,
  );
  const landThreshold = isAp ? 150 : 100;
  const landPrimary = num(landRatioText);
  // land100_ratio が「1.87」倍率表記のとき % に直す
  const landPrimaryPct =
    landPrimary == null
      ? null
      : landPrimary < 10
        ? Math.round(landPrimary * 100)
        : Math.round(landPrimary);
  let landVerdict = "材料不足";
  if (landPrimaryPct != null) {
    if (landPrimaryPct >= landThreshold) {
      landVerdict = `クリア（${landPrimaryPct}% ≥ ${landThreshold}%）→ 積算で価格を説明しやすい`;
    } else if (landPrimaryPct >= landThreshold * 0.85) {
      landVerdict = `惜しい（${landPrimaryPct}%／基準${landThreshold}%）→ 交渉・補正で届くか`;
    } else {
      landVerdict = `未達（${landPrimaryPct}% ＜ ${landThreshold}%）→ 土地値だけでは弱い`;
    }
  }

  const yRaw = deal.yield_pct;
  let yPct: number | null = null;
  if (yRaw != null && Number.isFinite(Number(yRaw))) {
    const n = Number(yRaw);
    yPct = n < 1.5 ? n * 100 : n;
  }
  // 独自調査（S3需給・ペルソナ）の想定利回り
  const yi =
    sj.yield_info && typeof sj.yield_info === "object"
      ? (sj.yield_info as Record<string, unknown>)
      : {};
  const isEst =
    String(yi.type || "") === "estimated" ||
    Boolean(yi.yield_range) ||
    Boolean(yi.monthly_rent_range);
  let estText = isEst && yi.yield_range ? String(yi.yield_range) : "";
  if (isEst && !estText && yi.yield_pct != null) {
    estText = `${Number(yi.yield_pct)}%`;
  }
  const estRent = yi.monthly_rent_range ? String(yi.monthly_rent_range) : "";
  const estSrc = yi.source ? String(yi.source) : "";
  const estDisplay = estText
    ? estText +
      (estRent ? `（想定家賃 ${estRent}）` : "") +
      (estSrc ? `／${estSrc}` : "")
    : "—";
  const estMatch = estText.match(/\d+(?:\.\d+)?/);
  const estPct = estMatch ? Number(estMatch[0]) : null;

  const yGate = isAp ? 8 : 10;
  const verdictVal = estPct != null ? estPct : yPct;
  const verdictLabel = estPct != null ? "想定" : "表面";
  let yVerdict = "材料不足（賃料・利回りが無い）";
  let yText = "—";
  if (yPct != null) yText = `${Number(yPct.toFixed(2))}%`;
  if (verdictVal != null) {
    if (verdictVal >= yGate) {
      yVerdict = `クリア（${verdictLabel} ${verdictVal.toFixed(1)}% ≥ ${yGate}%）→ 利回り条件は通過`;
    } else if (verdictVal >= yGate - 1.5) {
      yVerdict = `惜しい（${verdictLabel} ${verdictVal.toFixed(1)}%／基準${yGate}%）→ 賃料・価格交渉で届くか`;
    } else {
      yVerdict = `未達（${verdictLabel} ${verdictVal.toFixed(1)}% ＜ ${yGate}%）→ 利回り単体では弱い`;
    }
  }

  const rows: [string, string][] = [
    ["所在", loc],
    ["価格", price],
    ["土地値", landValText],
    ["土地値率", landRatioText],
    ["土地値の判定", landVerdict],
    ["表面利回り（マイソク）", yText],
    ["想定利回り（独自調査）", estDisplay],
    ["利回りの判定", yVerdict],
    ["土地", pick("land_area")],
    ["路線価手法", pick("land_method")],
    ["建物", pick("building")],
    ["聞く/保留", pick("listen_value")],
    ["問合せ経路", pick("inquiry_action")],
    ["score", deal.match_score != null ? String(deal.match_score) : "—"],
  ];
  const hazEval = pick("hazard_eval");
  const hazParts: [string, string][] = [
    ["洪水", pick("hazard_flood")],
    ["高潮", pick("hazard_storm_surge")],
    ["急傾斜", pick("hazard_landslide")],
    ["内水", pick("hazard_inland")],
  ];
  const hazFilled = hazParts.filter(([, v]) => v && v !== "—");
  const hasLand =
    pick("land_appraisal_man") !== "—" || pick("land100_ratio") !== "—";
  let hazStatus = "未調査";
  if (hazEval !== "—") {
    hazStatus = `調査済（総合=${hazEval}）`;
  } else if (hazFilled.length) {
    hazStatus = "部分のみ（総合判定なし）";
  } else if (hasLand) {
    hazStatus =
      "未着（土地値はあるがGrok調査にハザード項目なし＝調べて無しではなく未記載／取込漏れの可能性）";
  }
  rows.splice(
    8,
    0,
    ["ハザード状態", hazStatus],
    ["ハザード総合", hazEval],
    ...hazFilled,
  );
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

  const eventsHtml = events.length
    ? events
        .map((e) => {
          const label =
            EVENT_LABEL[String(e.event_type || "")] || String(e.event_type || "");
          const src = e.actor ? `（${esc(String(e.actor))}）` : "";
          const s = e.summary
            ? ` ${esc(String(e.summary).replace(/\n/g, " "))}`
            : "";
          return `<li><span class="t">${esc(fmtWhen(e.occurred_at))}</span> ${esc(label)}${src}${s}</li>`;
        })
        .join("\n")
    : `<li class="note">履歴はまだありません。</li>`;

  const landKind = isAp ? "AP（目安150%前後）" : "戸建（目安100%超）";
  const yKind = isAp ? "AP（聞くゲート≥8%）" : "戸建（聞くゲート≥10%）";

  return `<!doctype html><html lang="ja"><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>判断材料 — ${title}</title>
<style>
  body{font-family:system-ui,-apple-system,sans-serif;margin:0;padding:1.25rem;background:#f8fafc;color:#0f172a}
  .wrap{max-width:40rem;margin:0 auto;background:#fff;border-radius:12px;padding:1.25rem 1.25rem 1.5rem;box-shadow:0 1px 3px rgba(0,0,0,.08)}
  h1{font-size:1.1rem;margin:0 0 .75rem;line-height:1.4}
  h2{font-size:.95rem;margin:1.4rem 0 .5rem;color:#334155}
  table{width:100%;border-collapse:collapse;font-size:.9rem}
  th,td{border-bottom:1px solid #e2e8f0;padding:.55rem .4rem;vertical-align:top;text-align:left}
  th{width:7.5rem;color:#64748b;font-weight:600;white-space:nowrap}
  td{word-break:break-word}
  .actions{display:flex;flex-direction:column;gap:1.1rem;margin-top:1.25rem;align-items:stretch}
  .actions a{display:block;padding:.85rem 1.1rem;border-radius:8px;text-decoration:none;font-weight:600;font-size:.95rem;text-align:center}
  .yes{background:#059669;color:#fff}
  .no{background:#e2e8f0;color:#334155}
  .detail{background:#fff;color:#334155;border:1px solid #cbd5e1}
  .note{margin-top:1rem;font-size:.8rem;color:#64748b}
  .who{background:#f1f5f9;border-radius:8px;padding:.75rem .9rem;margin:0 0 1rem;font-size:.82rem;line-height:1.55;color:#334155}
  .who strong{color:#0f172a}
  .axis{display:grid;grid-template-columns:1fr 1fr;gap:.6rem;margin:0 0 1rem}
  .axis .card{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:.65rem .75rem;font-size:.82rem;line-height:1.45}
  .axis .lab{font-size:.72rem;color:#64748b;font-weight:600;margin-bottom:.2rem}
  .axis .val{font-weight:700;font-size:.95rem}
  .axis .vd{margin-top:.25rem;color:#334155}
  @media (max-width:420px){.axis{grid-template-columns:1fr}}
  ul.ev{list-style:none;margin:0;padding:0;font-size:.85rem}
  ul.ev li{padding:.35rem 0;border-bottom:1px solid #f1f5f9;line-height:1.5}
  ul.ev .t{color:#64748b;font-variant-numeric:tabular-nums;margin-right:.35rem}
</style>
<body><div class="wrap">
<div class="who">
  <strong>114・物件一次判定係</strong>の判断ページです。<br/>
  調査元=<strong>Grok S1</strong> → 振分・通知=<strong>114</strong> → あなたの Yes/No → 送信=<strong>511</strong>。<br/>
  Grok Bot のチャットでも、Cursor 本人でもありません。
</div>
<h1>${title}</h1>
<div class="axis">
  <div class="card">
    <div class="lab">土地値の評価（${esc(landKind)}）</div>
    <div class="val">${esc(landPrimaryPct != null ? `${landPrimaryPct}%` : landRatioText === "—" ? "率未記載" : landRatioText.split("（")[0])}</div>
    <div class="vd">${esc(landVerdict)}</div>
  </div>
  <div class="card">
    <div class="lab">利回りの評価（${esc(yKind)}）</div>
    <div class="val">${esc(yText === "—" ? "未記載" : yText)}</div>
    <div class="vd">${esc(yVerdict)}</div>
  </div>
</div>
<table><tbody>${tr}</tbody></table>
<div class="actions">
  <a class="yes" href="${yes}">問合せする（Yes）</a>
  <a class="no" href="${no}">見送り（No）</a>
</div>
<p class="note">押し間違え防止のため、ボタンは縦に間を空けています。</p>
<h2>問合せ・判断履歴</h2>
<ul class="ev">${eventsHtml}</ul>
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
    .select("id, title, price_man, yield_pct, structure, match_score, area, summary_json")
    .eq("id", dealId)
    .maybeSingle();
  if (error || !data) return null;
  return data as DealRow;
}

export async function fetchDealEvents(
  dealId: string,
  limit = 20,
): Promise<DealEvent[]> {
  const sb = createServiceClient();
  if (!sb) return [];
  const { data, error } = await sb
    .from("kurashift_re_deal_events")
    .select("event_type, actor, summary, occurred_at")
    .eq("deal_id", dealId)
    .order("occurred_at", { ascending: false })
    .limit(limit);
  if (error) return [];
  return (data || []) as DealEvent[];
}

/** Supabase の英語エラーを Slack 向けの日本語に直す（原文は末尾に短く残す） */
export function toJapaneseDbError(msg: string | undefined | null): string {
  const raw = (msg || "").trim();
  if (!raw) return "データベースの応答がありません（問合せは送っていません）";
  if (/exceed_egress_quota|restricted due to the following violations/i.test(raw)) {
    return "Supabase の無料枠（通信量）を使い切り、一時停止中でした。\n問合せは送っていません。枠が戻ったらもう一度押してください。";
  }
  if (/fetch failed|ENOTFOUND|ECONNREFUSED|ETIMEDOUT|timeout/i.test(raw)) {
    return `データベースにつながりませんでした（問合せは送っていません）。\n少し待ってもう一度押してください。\n原文: ${raw.slice(0, 80)}`;
  }
  return `データベースのエラーです（問合せは送っていません）。\n原文: ${raw.slice(0, 120)}`;
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
    return {
      ok: false,
      message: error ? toJapaneseDbError(error.message) : "対象の案件が見つかりません",
    };
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

  // yes（No/passed のあともやり直し可）
  if (prevDecision !== "no") {
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
  }

  const idempotencyKey =
    prevDecision === "no"
      ? `${dealId}:first_inquiry:retry_after_no`
      : `${dealId}:first_inquiry`;
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
  // Noやり直し時は旧ジョブがあっても新規キューを積む
  if (dup && prevDecision !== "no") {
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

  delete sj.auto_pass_reason;
  sj.inquiry_status = "sending";
  sj.property_gate = { ...prevGate, decision: "yes", at: now, source };
  const reopen =
    String(row.status || "") === "passed" || prevDecision === "no";
  await sb
    .from("kurashift_re_deals")
    .update({
      ...(reopen ? { status: "info" } : {}),
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
    return { ok: false, message: toJapaneseDbError(jobErr.message) };
  }
  return {
    ok: true,
    message: `問合せ送信をキューしました: ${title}`,
    job_id: job?.id ? String(job.id) : undefined,
  };
}
