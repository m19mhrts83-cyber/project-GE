import fs from "fs";
import path from "path";

export type InquiryAutoConfig = {
  version?: number;
  daily_send_cap?: number;
  tier3_auto_send?: { enabled?: boolean };
  tiers?: {
    tier0_exclude_inquiry_status?: string[];
    tier1_candidate?: {
      min_score?: number;
      grok_listen_values?: string[];
      require_inquiry_status?: string[];
    };
    tier2_daily_queue?: {
      enabled?: boolean;
      min_score?: number;
      grok_listen?: string;
      hazard_eval_not?: string;
    };
    tier3_auto_send?: {
      min_score?: number;
      grok_listen?: string;
      hazard_eval?: string;
      land100_not?: string;
    };
  };
  inquiry_candidate_overrides?: {
    grok_listen_values?: string[];
    revive_passed_status?: boolean;
    exclude_auto_pass_reasons?: string[];
  };
  production_filter?: {
    exclude_title_substrings?: string[];
    exclude_e2e_markers?: string[];
  };
};

const DEFAULT_CONFIG: InquiryAutoConfig = {
  daily_send_cap: 5,
  tier3_auto_send: { enabled: false },
  tiers: {
    tier0_exclude_inquiry_status: ["sending", "awaiting_reply", "has_reply"],
    tier1_candidate: {
      min_score: 2.0,
      grok_listen_values: ["聞く", "保留"],
      require_inquiry_status: ["none", "draft", ""],
    },
    tier2_daily_queue: {
      enabled: true,
      min_score: 5.0,
      grok_listen: "聞く",
      hazard_eval_not: "除外",
    },
    tier3_auto_send: {
      min_score: 7.0,
      grok_listen: "聞く",
      hazard_eval: "OK",
      land100_not: "見送り",
    },
  },
  inquiry_candidate_overrides: {
    grok_listen_values: ["聞く", "保留"],
    revive_passed_status: true,
    exclude_auto_pass_reasons: ["mansion_unit", "subject_noise"],
  },
};

export function loadInquiryAutoConfig(): InquiryAutoConfig {
  const candidates = [
    path.join(process.cwd(), "..", "..", "config", "kurashift_re_inquiry_auto.yaml"),
    path.join(process.cwd(), "config", "kurashift_re_inquiry_auto.yaml"),
  ];
  for (const p of candidates) {
    try {
      if (!fs.existsSync(p)) continue;
      const raw = fs.readFileSync(p, "utf8");
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const { parse } = require("yaml") as typeof import("yaml");
      const parsed = parse(raw) as InquiryAutoConfig;
      return {
        ...DEFAULT_CONFIG,
        ...parsed,
        tiers: { ...DEFAULT_CONFIG.tiers, ...parsed.tiers },
        inquiry_candidate_overrides: {
          ...DEFAULT_CONFIG.inquiry_candidate_overrides,
          ...parsed.inquiry_candidate_overrides,
        },
      };
    } catch {
      /* try next */
    }
  }
  return DEFAULT_CONFIG;
}
