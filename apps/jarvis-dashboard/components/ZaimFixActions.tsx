"use client";

import { useTransition } from "react";
import { confirmZaimFix } from "@/app/actions/zaimWatch";

export default function ZaimFixActions({
  fixId,
  flagged = false,
  path = "/zaim",
}: {
  fixId: string;
  flagged?: boolean;
  path?: string;
}) {
  const [pending, start] = useTransition();

  return (
    <div style={{ display: "flex", gap: 6, flexShrink: 0, alignItems: "center" }}>
      {flagged ? (
        <span className="meta" style={{ color: "var(--warn)", fontWeight: 600 }}>
          学習が違う
        </span>
      ) : null}
      <button
        type="button"
        className="btn"
        disabled={pending}
        style={{
          padding: "4px 10px",
          fontSize: "0.78rem",
          color: flagged ? undefined : "var(--warn)",
        }}
        onClick={() =>
          start(async () => {
            await confirmZaimFix(
              fixId,
              flagged ? "pending_confirm" : "disputed",
              path,
            );
          })
        }
      >
        {flagged ? "フラグ解除" : "おかしい"}
      </button>
    </div>
  );
}
