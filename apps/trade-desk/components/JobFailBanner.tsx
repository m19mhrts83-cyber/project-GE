"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { FailBannerItem, SendingStuckItem } from "@/lib/jobFailVisibility";
import { FAIL_JOB_LABEL } from "@/lib/jobFailVisibility";

export default function JobFailBanner({
  failed,
  sendingStuck,
}: {
  failed: FailBannerItem[];
  sendingStuck: SendingStuckItem[];
}) {
  const router = useRouter();
  const [busyId, setBusyId] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  if (failed.length === 0 && sendingStuck.length === 0) return null;

  async function ack(jobId: string) {
    setBusyId(jobId);
    setErr(null);
    try {
      const res = await fetch(`/api/jobs/${jobId}/ack`, { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setErr(data.error || "確認の記録に失敗しました");
        return;
      }
      router.refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "エラー");
    } finally {
      setBusyId(null);
    }
  }

  const showFailed = failed.slice(0, 5);
  const moreFailed = Math.max(0, failed.length - showFailed.length);
  const showStuck = sendingStuck.slice(0, 5);
  const moreStuck = Math.max(0, sendingStuck.length - showStuck.length);

  return (
    <div
      className="card"
      role="alert"
      style={{
        marginTop: 12,
        borderColor: "var(--danger, #b45309)",
        background: "color-mix(in srgb, var(--danger, #b45309) 8%, transparent)",
      }}
    >
      <header>
        <span className="lvl">要確認</span>
        <strong>送信ジョブの失敗・滞留</strong>
      </header>
      <p className="meta" style={{ marginTop: 6 }}>
        「キュー投入」はまだ Gmail 送信完了ではありません。失敗時はここと案件画面で気づけるようにしています。Jarvis
        チャットで原因を直し、案件から再キューしてください。
      </p>

      {failed.length > 0 ? (
        <div style={{ marginTop: 10 }}>
          <p style={{ margin: 0, fontWeight: 600 }}>
            {FAIL_JOB_LABEL[failed[0].jobType] || failed[0].jobType}
            に失敗したジョブがあります（{failed.length}件）。状況を確認してください。
          </p>
          <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>
            {showFailed.map((f) => (
              <li key={f.jobId} style={{ marginBottom: 6 }}>
                <a href={`/realestate/deals?deal=${encodeURIComponent(f.dealId)}`}>
                  {f.dealTitle}
                </a>
                {f.errorText ? (
                  <span className="meta"> — {f.errorText.slice(0, 80)}</span>
                ) : null}{" "}
                <button
                  type="button"
                  className="btn"
                  style={{ fontSize: 11, padding: "2px 8px" }}
                  disabled={busyId === f.jobId}
                  onClick={() => ack(f.jobId)}
                >
                  {busyId === f.jobId ? "…" : "確認した"}
                </button>
              </li>
            ))}
          </ul>
          {moreFailed > 0 ? (
            <p className="meta" style={{ marginTop: 4 }}>
              他 {moreFailed} 件 → <a href="/realestate/deals">案件一覧</a>
            </p>
          ) : null}
        </div>
      ) : null}

      {sendingStuck.length > 0 ? (
        <div style={{ marginTop: 12 }}>
          <p style={{ margin: 0, fontWeight: 600 }}>
            送信中のまま止まっている案件があります（{sendingStuck.length}件）。確認してください。
          </p>
          <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>
            {showStuck.map((s) => (
              <li key={s.dealId}>
                <a href={`/realestate/deals?deal=${encodeURIComponent(s.dealId)}`}>
                  {s.dealTitle}
                </a>
                <span className="meta">
                  {" "}
                  — sending のまま
                  {s.updatedAt ? `（更新 ${s.updatedAt.slice(0, 16)}）` : ""}
                </span>
              </li>
            ))}
          </ul>
          {moreStuck > 0 ? (
            <p className="meta" style={{ marginTop: 4 }}>
              他 {moreStuck} 件 → <a href="/realestate/deals">案件一覧</a>
            </p>
          ) : null}
        </div>
      ) : null}

      <p className="meta" style={{ marginTop: 10 }}>
        補助: <a href="/jobs">ジョブ一覧</a>
      </p>
      {err ? (
        <p className="meta" style={{ marginTop: 6, color: "var(--danger, #b45309)" }}>
          {err}
        </p>
      ) : null}
    </div>
  );
}
