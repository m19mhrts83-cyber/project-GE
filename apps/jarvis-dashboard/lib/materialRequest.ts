/**
 * 「資料を送ってください」系の依頼を検出し、依頼品目を抜き出す（LLM なし）。
 * scripts/jarvis_material_request.py と同じ規則。
 */

const REQUEST_RE =
  /(ご提出|ご送付|お送り(いただ|くださ)|ご準備|ご用意|添付(して|の上)|送って(いただ|くださ)|ご提示)/;
const MATERIAL_RE = /(資料|書類|証明書|写し|コピー|通帳|申込書|申告書|明細|図面|謄本|見積)/;
const LEAD_RE = /(下記|以下|次の).{0,20}(資料|書類|ご提出|ご準備|ご用意|お願い)/;
const BULLET_RE = /^\s*(?:[・•\-*]|[0-9０-９]+[.．)）]|[①-⑳])\s*(.+)$/;
const QUOTE_RE =
  /^(>|-{3,}\s*Original|From:|差出人:|\d{4}年\d{1,2}月\d{1,2}日.*\d{1,2}:\d{2})/;
const CLOSE_RE = /(よろしくお願い|宜しくお願い|以上|ご確認のほど)/;
const SEPARATOR_PREFIXES = ["＊", "*", "■", "━", "＝", "=", "-----"];
const MAX_ITEMS = 10;

function mainLines(body: string): string[] {
  const out: string[] = [];
  for (const line of String(body || "").split(/\r?\n/)) {
    if (QUOTE_RE.test(line.trim())) break;
    out.push(line.trimEnd());
  }
  return out;
}

/** 依頼された資料の品目。依頼でなければ空配列。 */
export function extractMaterialRequests(body: string | null | undefined): string[] {
  const lines = mainLines(String(body || ""));
  const text = lines.join("\n");
  if (!(REQUEST_RE.test(text) && MATERIAL_RE.test(text))) return [];
  const items: string[] = [];
  let inBlock = false;
  let blockN = 0;
  for (const line of lines) {
    const s = line.trim().replace(/^　+|　+$/g, "");
    if (!s) {
      // 一覧の後の空行で区切る（一覧の前の空行は許す）
      if (inBlock && blockN) inBlock = false;
      continue;
    }
    if (SEPARATOR_PREFIXES.some((p) => s.startsWith(p))) {
      if (inBlock && blockN) inBlock = false;
      continue;
    }
    if (s.startsWith("※") || s.startsWith("（※") || s.startsWith("(※")) continue;
    const m = s.match(BULLET_RE);
    if (m && (inBlock || MATERIAL_RE.test(s))) {
      items.push(m[1].trim());
      blockN++;
      continue;
    }
    if (LEAD_RE.test(s)) {
      inBlock = true;
      blockN = 0;
      continue;
    }
    if (inBlock) {
      if (CLOSE_RE.test(s) || s.length > 60) {
        inBlock = false;
        continue;
      }
      items.push(s);
      blockN++;
    }
  }
  const uniq = Array.from(new Set(items.map((x) => x.slice(0, 80)).filter(Boolean)));
  if (!uniq.length) {
    // 依頼文はあるが一覧が取れないときは、依頼のある1文を品目代わりに
    const one = lines.map((l) => l.trim()).find((l) => REQUEST_RE.test(l) && MATERIAL_RE.test(l));
    return one ? [one.slice(0, 80)] : [];
  }
  return uniq.slice(0, MAX_ITEMS);
}
