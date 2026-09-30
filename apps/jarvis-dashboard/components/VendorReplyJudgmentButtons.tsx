"use client";

import { useRouter } from "next/navigation";
import { useOptimistic, useTransition } from "react";
import {
  applyVendorReplyJudgment,
  resetVendorReplyJudgment,
} from "@/app/actions/triage";
import {
  VENDOR_JUDGMENT,
  type VendorJudgmentCode,
  type VendorJudgmentPayload,
} from "@/lib/vendorJudgment";
import { useToast } from "@/components/Toast";

type Props = {
  id: string;
  path: string;
  vendorId: string | null;
  judgment: VendorJudgmentPayload | null;
};

export default function VendorReplyJudgmentButtons({
  id,
  path,
  vendorId,
  judgment,
}: Props) {
  const router = useRouter();
  const toast = useToast();
  const [pending, start] = useTransition();
  const [optimisticJudgment, setOptimistic] =
    useOptimistic<VendorJudgmentPayload | null>(judgment);

  function apply(code: VendorJudgmentCode) {
    start(async () => {
      const prev = optimisticJudgment;
      const meta = VENDOR_JUDGMENT[code];
      setOptimistic({
        code,
        label: meta.label,
        at: new Date().toISOString(),
        vendor_id: vendorId || "",
      });
      const r = await applyVendorReplyJudgment(id, code, path);
      if (!r.ok) {
        toast.push(r.error, "err");
        setOptimistic(prev);
        router.refresh();
        return;
      }
      toast.push(r.toast || meta.toast, {
        undo: async () => {
          await resetVendorReplyJudgment(id, path);
          router.refresh();
        },
      });
      if (r.message && r.message !== r.toast) {
        toast.push(r.message, "info");
      }
      router.refresh();
    });
  }

  function reset() {
    start(async () => {
      const prev = optimisticJudgment;
      setOptimistic(null);
      const r = await resetVendorReplyJudgment(id, path);
      if (!r.ok) {
        toast.push(r.error, "err");
        setOptimistic(prev);
        router.refresh();
        return;
      }
      toast.push("未読に戻しました");
      router.refresh();
    });
  }

  if (optimisticJudgment) {
    return (
      <div
        className="triage-actions vendor-judgment-actions"
        style={{ marginLeft: "auto", flexWrap: "wrap", gap: 6 }}
      >
        <span
          className="status-badge"
          style={{
            background: "#ecfdf5",
            border: "1px solid #a7f3d0",
            color: "#065f46",
          }}
        >
          {optimisticJudgment.label}
        </span>
        <button
          type="button"
          className="btn"
          style={{ padding: "4px 10px", fontSize: "0.78rem", color: "var(--ink)" }}
          disabled={pending}
          onClick={reset}
        >
          やり直す
        </button>
      </div>
    );
  }

  return (
    <div
      className="triage-actions vendor-judgment-actions"
      style={{ marginLeft: "auto", flexWrap: "wrap", gap: 6 }}
    >
      <button
        type="button"
        className="btn primary"
        style={{ padding: "4px 10px", fontSize: "0.78rem" }}
        disabled={pending}
        onClick={() => apply("await_staff")}
      >
        返信不要・担当待ち
      </button>
      <button
        type="button"
        className="btn"
        style={{ padding: "4px 10px", fontSize: "0.78rem", color: "var(--ink)" }}
        disabled={pending}
        onClick={() => apply("no_reply")}
      >
        返信不要（確認済）
      </button>
      <button
        type="button"
        className="btn"
        style={{ padding: "4px 10px", fontSize: "0.78rem", color: "var(--ink)" }}
        disabled={pending}
        onClick={() => apply("later")}
      >
        後で見る
      </button>
    </div>
  );
}
