"use client";

import { useTransition } from "react";
import { confirmZaimFix } from "@/app/actions/zaimWatch";

export default function ZaimFixActions({
  fixId,
  path = "/zaim",
}: {
  fixId: string;
  path?: string;
}) {
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
            await confirmZaimFix(fixId, "confirmed", path);
          })
        }
      >
        確認OK
      </button>
      <button
        type="button"
        className="btn"
        disabled={pending}
        style={{
          padding: "4px 10px",
          fontSize: "0.78rem",
          color: "var(--warn)",
        }}
        onClick={() =>
          start(async () => {
            const note =
              typeof window !== "undefined"
                ? window.prompt(
                    "どこがおかしいか（任意）。空でも「おかしい」として記録します。",
                    "",
                  )
                : null;
            if (note === null) return; // キャンセル
            await confirmZaimFix(fixId, "disputed", path, note.trim() || undefined);
          })
        }
      >
        おかしい
      </button>
    </div>
  );
}
