export const BAIRITSU_MARKER = "【倍率地域のため】";

export type ReInquiryTemplate = {
  subject_template?: string;
  body_template?: string;
  body_append_bairitsu?: string;
  signature_template?: string;
  from_account?: string;
  title_short_max?: number;
};

export const DEFAULT_RE_INQUIRY_TEMPLATE: ReInquiryTemplate = {
  subject_template: "物件資料のご依頼（{title_short}）",
  body_template: [
    "お世話になっております。物件情報の送付をよろしくお願いします。",
    "併せて、固定資産評価額、修繕履歴(時期/内容/金額)が分かる資料も送付いただけると幸いです。",
    "差し支えなければ、以下についてもご教授ください。よろしくお願いします。",
    "・売却理由",
    "・売却希望時期",
    "・価格交渉可能でしょうか",
    "",
    "{signature}",
  ].join("\n"),
  body_append_bairitsu: [
    `${BAIRITSU_MARKER}固定資産税の課税明細（または固定資産評価額が確認できる資料）を`,
    "併せてご送付いただけますでしょうか。土地積算の確認に必要です。",
  ].join("\n"),
  title_short_max: 40,
};

export function isLandMethodBairitsu(
  landMethod: string | null | undefined
): boolean {
  return Boolean(landMethod && landMethod.includes("倍率"));
}

function parseEmailFromRaw(fromRaw: string | undefined | null): string {
  if (!fromRaw) return "";
  const m = fromRaw.match(/<([^>]+)>/);
  return (m ? m[1] : fromRaw).trim();
}

function grokFromSummary(
  summaryJson: Record<string, unknown> | null | undefined
): Record<string, unknown> | null {
  if (!summaryJson || typeof summaryJson !== "object") return null;
  const grok = summaryJson.grok;
  if (!grok || typeof grok !== "object") return null;
  return grok as Record<string, unknown>;
}

export function appendBairitsuBlock(
  body: string,
  tmpl: ReInquiryTemplate
): string {
  const extra = String(tmpl.body_append_bairitsu || "").trim();
  if (!extra || body.includes(BAIRITSU_MARKER)) return body;
  const lines = body.split("\n");
  let sigIdx = lines.length;
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    const line = lines[i]?.trim() || "";
    if (
      line &&
      !line.startsWith("・") &&
      !line.includes("お世話") &&
      !line.includes("併せて")
    ) {
      if (i >= lines.length - 3) {
        sigIdx = i;
        break;
      }
    }
  }
  const head = lines.slice(0, sigIdx).join("\n").trimEnd();
  const tail = lines.slice(sigIdx).join("\n").trim();
  let merged = `${head}\n\n${extra}`;
  if (tail) merged = `${merged}\n\n${tail}`;
  return merged.trim();
}

export function buildInquiryPreviewFromTemplate(
  tmpl: ReInquiryTemplate,
  params: {
    title: string;
    summaryJson?: Record<string, unknown> | null;
    fromRaw?: string | null;
    toEmail?: string | null;
    signatureName?: string | null;
  }
): {
  to: string;
  subject: string;
  body: string;
  land_method: string | null;
  land_method_bairitsu: boolean;
} {
  const title = params.title || "物件";
  const maxLen = Number(tmpl.title_short_max || 40);
  const titleShort =
    title.length <= maxLen ? title : `${title.slice(0, maxLen - 1)}…`;
  const subject = String(
    tmpl.subject_template || "物件資料のご依頼（{title_short}）"
  ).replace("{title_short}", titleShort);

  const signature = String(params.signatureName || "").trim();
  let body = String(tmpl.body_template || "")
    .replace("{signature}", signature)
    .trim();

  const grok = grokFromSummary(params.summaryJson);
  const landMethod =
    grok && typeof grok.land_method === "string" ? grok.land_method : null;
  const bairitsu = isLandMethodBairitsu(landMethod);
  if (bairitsu) {
    body = appendBairitsuBlock(body, tmpl);
  }

  const to =
    String(params.toEmail || "").trim() ||
    parseEmailFromRaw(params.fromRaw) ||
    parseEmailFromRaw(
      typeof params.summaryJson?.from === "string"
        ? params.summaryJson.from
        : undefined
    );

  return {
    to,
    subject,
    body,
    land_method: landMethod,
    land_method_bairitsu: bairitsu,
  };
}

export function buildGrokInvestigatePrompt(params: {
  title: string;
  area?: string | null;
  priceMan?: number | null;
  summaryJson?: Record<string, unknown> | null;
  dealId?: string | null;
}): string {
  const grok = grokFromSummary(params.summaryJson);
  const location =
    (grok && typeof grok.location === "string" ? grok.location : "") ||
    params.area ||
    params.title;
  const price =
    (grok && typeof grok.price_man_raw === "string"
      ? grok.price_man_raw
      : null) ||
    (params.priceMan != null ? String(params.priceMan) : "") ||
    (grok && grok.price_man != null ? String(grok.price_man) : "");
  const url =
    (params.summaryJson &&
      typeof params.summaryJson.url === "string" &&
      params.summaryJson.url) ||
    (params.summaryJson &&
      typeof params.summaryJson.listing_url === "string" &&
      params.summaryJson.listing_url) ||
    (grok && typeof grok.url === "string" && grok.url) ||
    "";
  const label =
    params.title.length <= 40
      ? params.title
      : `${params.title.slice(0, 39)}…`;

  return [
    "調査追加: " + label,
    `住所: ${location}`,
    price ? `価格: ${price}万` : "価格: （不明）",
    url ? `URL: ${url}` : null,
    params.dealId ? `deal_id: ${params.dealId}` : null,
    "",
    "（以下は不動産賃貸チーム / 参謀向け。@物件調査 に振って路線価・ハザードを調査）",
    "",
    "【物件調査 — 必須2調査】",
    "",
    "以下の物件について調査し、完了後 matsuno.estate@gmail.com 宛に",
    "件名 `[Grok調査] {市区町村} {短名}` でメール送信してください（承認不要）。",
    "本文は下記テンプレに厳密準拠。",
    "",
    "## 調査対象（入力）",
    `- 所在: ${location}`,
    price ? `- 価格_万: ${price}` : "- 価格_万: （メール等から読取）",
    params.title ? `- 案件タイトル: ${params.title}` : "",
    url ? `- URL: ${url}` : "",
    "",
    "1) 相続税路線価: chikamap → 倍率なら国税庁路線価図。方式は 路線価|倍率 を必ず記載",
    "2) ハザード: disaportal.gsi.go.jp/maps/ で洪水/土砂/高潮/内水 → 評価 OK|注意|除外",
    "",
    "## 物件",
    "- 所在:",
    "- 価格_万:",
    "- 土地面積:",
    "- 建物:",
    "- 駐車場: あり|なし|不明",
    "- URL:",
    "",
    "## 土地評価",
    "- 方式: 路線価|倍率",
    "- 路線価_万円_坪:",
    "- 倍率:",
    "- 土地積算_万円:",
    "- 土地値100%_比率:",
    "- 土地値100%判定: 聞く|保留|見送り",
    "- 根拠URL:",
    "",
    "## ハザード（重ねるハザードマップ）",
    "- 調査URL: https://disaportal.gsi.go.jp/maps/",
    "- 洪水: なし|該当|要確認",
    "- 土砂: なし|該当|要確認",
    "- 高潮: なし|該当|要確認",
    "- 内水: なし|該当|要確認",
    "- 評価: OK|注意|除外",
    "- 根拠URL:",
    "",
    "## 人口（チャプロ軸）",
    "- 評価: 安全|選別|攻め",
    "",
    "## 総合",
    "- 聞く価値: 聞く|保留|見送り",
    "- 理由1行:",
  ]
    .filter((line) => line != null)
    .join("\n");
}
