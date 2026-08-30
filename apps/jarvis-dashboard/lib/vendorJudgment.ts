import type { TriageStatus } from "@/lib/triageStatus";

/** 地場業者返信メールの判断コード（payload.vendor_judgment.code） */
export type VendorJudgmentCode = "await_staff" | "no_reply" | "later";

export type VendorJudgmentMeta = {
  code: VendorJudgmentCode;
  label: string;
  status: TriageStatus;
  toast: string;
  notePrefix: string;
};

export const VENDOR_JUDGMENT: Record<VendorJudgmentCode, VendorJudgmentMeta> = {
  await_staff: {
    code: "await_staff",
    label: "担当待ち",
    status: "skipped",
    toast: "担当待ちとして記録しました",
    notePrefix: "返信判断: 担当待ち",
  },
  no_reply: {
    code: "no_reply",
    label: "確認済",
    status: "skipped",
    toast: "返信不要（確認済）として記録しました",
    notePrefix: "返信判断: 返信不要（確認済）",
  },
  later: {
    code: "later",
    label: "後で",
    status: "snoozed",
    toast: "後で見るにしました",
    notePrefix: "返信判断: 後で確認",
  },
};

export type VendorJudgmentPayload = {
  code: VendorJudgmentCode;
  label: string;
  at: string;
  vendor_id: string;
};

export function parseVendorJudgment(
  raw: unknown,
): VendorJudgmentPayload | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const o = raw as Record<string, unknown>;
  const code = o.code;
  if (code !== "await_staff" && code !== "no_reply" && code !== "later") {
    return null;
  }
  return {
    code,
    label: typeof o.label === "string" ? o.label : VENDOR_JUDGMENT[code].label,
    at: typeof o.at === "string" ? o.at : "",
    vendor_id: typeof o.vendor_id === "string" ? o.vendor_id : "",
  };
}
