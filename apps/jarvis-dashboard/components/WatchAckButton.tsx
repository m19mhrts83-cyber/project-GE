"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { acknowledgeWatch } from "@/app/actions/watchAck";
import {
  canShowGenericAckButton,
  formatQuietUntilLabel,
  isWatchAckActive,
  buildWatchAckFingerprint,
  readUserAck,
  type WatchAckRow,
} from "@/lib/watchUserAck";

export default function WatchAckButton({
  watchId,
  level,
  summary,
  payload,
}: {
  watchId: string;
  level?: string | null;
  summary?: string | null;
  payload?: Record<string, unknown> | null;
}) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [err, setErr] = useState<string | null>(null);

  const row: WatchAckRow = {
    id: watchId,
    level,
    summary,
    status: "active",
    payload: payload || null,
  };
  const fp = buildWatchAckFingerprint(row);
  const acked = isWatchAckActive(payload, fp);
  const ua = readUserAck(payload);
  const showBtn = canShowGenericAckButton(row);

  if (acked) {
    const until = formatQuietUntilLabel(ua?.quiet_until);
    return (
      <p className="meta watch-ack-done">
        確認済{until ? ` · ${until}までバッジ抑制` : ""}
        （進展または期限で再表示）
      </p>
    );
  }

  if (!showBtn) return null;

  return (
    <div className="watch-ack-wrap">
      <button
        type="button"
        className="btn"
        disabled={pending}
        onClick={() => {
          setErr(null);
          start(async () => {
            const r = await acknowledgeWatch(watchId);
            if (!r.ok) {
              setErr(r.error || "確認に失敗しました");
              return;
            }
            router.refresh();
          });
        }}
      >
        {pending ? "更新中…" : "確認した"}
      </button>
      {err ? <p className="meta err">{err}</p> : null}
    </div>
  );
}
