"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { fmtYen } from "@/lib/format";
import {
  FUND_MOVE_UX,
  RAIL_STATUS_LABEL,
  type TransferRailStatus,
} from "@/lib/cardSettlementBuffer";

export type RailRow = {
  id?: string;
  label?: string;
  amount_jpy?: number;
  status?: string;
  otp_channel?: string;
  manual_iphone?: string;
  evidence?: string | null;
  last_error?: string | null;
  note?: string | null;
  remind_at?: string | null;
};

const QUICK: { status: TransferRailStatus; label: string }[] = [
  { status: "awaiting_final_confirm", label: "最終確認待ち" },
  { status: "waiting_user", label: "OTP待ち" },
  { status: "done", label: "完了" },
  { status: "deferred", label: "延期" },
  { status: "blocked", label: "ブロック" },
];

export default function MoneyOpRailsPanel({
  opId,
  rails,
  showUx = true,
}: {
  opId: string;
  rails: RailRow[];
  showUx?: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  async function patchRail(
    railId: string,
    status: TransferRailStatus,
    extra?: { note?: string }
  ) {
    setBusy(railId + status);
    setMsg(null);
    try {
      const res = await fetch(`/api/money-ops/${opId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          rail_id: railId,
          rail_status: status,
          note: extra?.note,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setMsg(data.error || "失敗");
      } else {
        setMsg(`${railId} → ${RAIL_STATUS_LABEL[status] || status}`);
        router.refresh();
      }
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "エラー");
    } finally {
      setBusy(null);
    }
  }

  if (!rails.length) return null;

  const remaining = rails.filter(
    (r) => r.status !== "done" && r.status !== "cancelled"
  );

  return (
    <div style={{ marginTop: 8 }}>
      {showUx ? (
        <div
          className="meta"
          style={{
            marginBottom: 8,
            padding: 8,
            borderRadius: 8,
            background: "var(--card-soft, #f6f6f4)",
          }}
        >
          <strong>{FUND_MOVE_UX.title}</strong>
          <ol style={{ margin: "6px 0 0", paddingLeft: 18 }}>
            {FUND_MOVE_UX.steps.map((s) => (
              <li key={s.id} style={{ marginBottom: 2 }}>
                {s.actor === "user" ? "あなた: " : "Jarvis: "}
                {s.label}
              </li>
            ))}
          </ol>
        </div>
      ) : null}

      {remaining.length > 0 ? (
        <div className="meta" style={{ marginBottom: 6, color: "#a40" }}>
          残り {remaining.length} レール
          {remaining
            .map((r) => r.label || r.id)
            .filter(Boolean)
            .slice(0, 3)
            .join(" / ")}
          {remaining.length > 3 ? "…" : ""}
        </div>
      ) : (
        <div className="meta" style={{ marginBottom: 6 }}>
          Phase1 レールはすべて完了（Phase2 以降は別途）
        </div>
      )}

      <ul className="meta" style={{ marginTop: 4, paddingLeft: 18 }}>
        {rails.map((r) => {
          const id = r.id || r.label || "?";
          const st = (r.status || "pending") as TransferRailStatus;
          const label = RAIL_STATUS_LABEL[st] || st;
          return (
            <li key={id} style={{ marginBottom: 10 }}>
              <strong>
                {(r.label || id) +
                  (r.amount_jpy != null ? ` ${fmtYen(Number(r.amount_jpy))}` : "")}
              </strong>
              {" · "}
              {label}
              {r.otp_channel ? ` · OTP:${r.otp_channel}` : ""}
              {r.remind_at ? (
                <div style={{ color: "#a40" }}>リマインド: {r.remind_at}</div>
              ) : null}
              {r.note ? <div>{r.note}</div> : null}
              {r.last_error ? (
                <div style={{ color: "#a40" }}>err: {r.last_error}</div>
              ) : null}
              {r.evidence ? <div>証跡: {r.evidence}</div> : null}
              {r.manual_iphone ? <div>{r.manual_iphone}</div> : null}
              {st !== "done" ? (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 4 }}>
                  {QUICK.map((q) => (
                    <button
                      key={q.status}
                      type="button"
                      className="btn"
                      disabled={busy != null}
                      onClick={() => patchRail(String(r.id || id), q.status)}
                      style={{ fontSize: 11, padding: "2px 6px" }}
                    >
                      {q.label}
                    </button>
                  ))}
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
      {msg ? <div className="meta">{msg}</div> : null}
    </div>
  );
}
