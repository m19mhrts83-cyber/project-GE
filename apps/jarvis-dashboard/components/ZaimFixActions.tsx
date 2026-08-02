"use client";

import { useTransition } from "react";
import { confirmZaimFix } from "@/app/actions/zaimWatch";

export default function ZaimFixActions({ fixId }: { fixId: string }) {
  const [pending, start] = useTransition();

  return (
    <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
      <button
        type="button"
        className="btn"
        disabled={pending}
        style={{ padding: "4px 10px", fontSize: "0.78rem" }}
        onClick={() =>
          start(async () => {
            await confirmZaimFix(fixId, "confirmed", "/zaim");
          })
        }
      >
        確認OK
      </button>
      <button
        type="button"
        className="btn"
        disabled={pending}
        style={{ padding: "4px 10px", fontSize: "0.78rem", color: "var(--warn)" }}
        onClick={() =>
          start(async () => {
            await confirmZaimFix(fixId, "disputed", "/zaim");
          })
        }
      >
        おかしい
      </button>
    </div>
  );
}
