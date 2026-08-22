import {
  loadInquiryAutoConfig,
  type InquiryAutoConfig,
} from "./reInquiryAutoConfig";
import type { ReDealForInquiry } from "./reInquiryCandidate";

const DEFAULT_E2E_MARKER = "E2E-GROK-KURASHIFT";

function sjOf(deal: ReDealForInquiry): Record<string, unknown> {
  const sj = deal.summary_json;
  return sj && typeof sj === "object" ? sj : {};
}

/** Tier2 等 — E2E fixture・テスト物件を除外（本番候補のみ） */
export function isProductionInquiryDeal(
  deal: ReDealForInquiry,
  cfg?: InquiryAutoConfig
): boolean {
  const config = cfg || loadInquiryAutoConfig();
  const pf = config.production_filter;
  const titleSubstrings =
    pf?.exclude_title_substrings ?? [DEFAULT_E2E_MARKER];
  const e2eMarkers = pf?.exclude_e2e_markers ?? [DEFAULT_E2E_MARKER];

  const title = String(deal.title || "");
  for (const sub of titleSubstrings) {
    if (sub && title.includes(sub)) return false;
  }

  const sj = sjOf(deal);
  const grok =
    sj.grok && typeof sj.grok === "object"
      ? (sj.grok as Record<string, unknown>)
      : null;
  const blob = [
    title,
    String(sj.e2e ?? ""),
    String(sj.report_id ?? ""),
    String(grok?.e2e ?? ""),
    String(grok?.report_id ?? ""),
  ].join("\n");

  for (const marker of e2eMarkers) {
    if (marker && blob.includes(marker)) return false;
  }

  return true;
}
