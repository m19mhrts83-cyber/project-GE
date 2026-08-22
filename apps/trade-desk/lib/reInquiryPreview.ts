import fs from "fs";
import path from "path";
import {
  DEFAULT_RE_INQUIRY_TEMPLATE,
  buildInquiryPreviewFromTemplate,
  type ReInquiryTemplate,
} from "./reInquiryShared";

export {
  BAIRITSU_MARKER,
  buildGrokInvestigatePrompt,
  isLandMethodBairitsu,
} from "./reInquiryShared";

export function loadReInquiryTemplate(): ReInquiryTemplate {
  const candidates = [
    path.join(process.cwd(), "..", "..", "config", "kurashift_re_inquiry_template.yaml"),
    path.join(process.cwd(), "config", "kurashift_re_inquiry_template.yaml"),
  ];
  for (const p of candidates) {
    try {
      if (!fs.existsSync(p)) continue;
      const raw = fs.readFileSync(p, "utf8");
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const { parse } = require("yaml") as typeof import("yaml");
      return { ...DEFAULT_RE_INQUIRY_TEMPLATE, ...(parse(raw) as ReInquiryTemplate) };
    } catch {
      /* try next */
    }
  }
  return DEFAULT_RE_INQUIRY_TEMPLATE;
}

export function buildInquiryPreview(params: {
  title: string;
  summaryJson?: Record<string, unknown> | null;
  fromRaw?: string | null;
  toEmail?: string | null;
  signatureName?: string | null;
}) {
  return buildInquiryPreviewFromTemplate(loadReInquiryTemplate(), params);
}
