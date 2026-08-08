"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import {
  refreshGluconScheduleFromKamiooya,
  setManualGluconDate,
} from "@/app/actions/glucon";
import type { GluconActiveCycle } from "@/lib/glucon/types";

export default function GluconScheduleHeader({
  cycle,
}: {
  cycle: GluconActiveCycle | null;
}) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [manualDate, setManualDate] = useState(cycle?.gluconDate || "");
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const urgent =
    cycle && cycle.daysUntilDeadline <= 7 && cycle.daysUntilDeadline >= 0;

  return (
    <section className={`card${urgent ? " glucon-urgent" : ""}`}>
      <header>
        <span className="lvl">日程</span>
        <strong>グルコン提出サイクル</strong>
      </header>
      {cycle ? (
        <ul className="meta" style={{ listStyle: "none", padding: 0, margin: "0.5rem 0" }}>
          <li>
            次回グルコン: <strong>{cycle.gluconDate}</strong>
            {" "}（{cycle.source}
            {cycle.estimated ? "・推定" : ""}）
          </li>
          <li>
            提出期限: <strong>{cycle.reportDeadline}</strong>
            {" "}（開催日−10日）／残り{" "}
            <strong>
              {cycle.daysUntilDeadline >= 0
                ? `${cycle.daysUntilDeadline}日`
                : `${Math.abs(cycle.daysUntilDeadline)}日超過`}
            </strong>
          </li>
          <li>
            Journal 抽出: {cycle.journalFrom}〜{cycle.journalTo}
            （前回期限〜今回期限）
          </li>
          <li>報告 period: {cycle.periodKey}</li>
          {cycle.title ? <li className="meta">{cycle.title}</li> : null}
        </ul>
      ) : (
        <p className="meta">日程未設定。WeStudy 取込後に更新するか、手動で開催日を入力してください。</p>
      )}

      <div className="qe-form-actions" style={{ gap: "0.5rem", flexWrap: "wrap" }}>
        <button
          type="button"
          className="btn"
          disabled={pending}
          onClick={() => {
            setErr(null);
            setMsg(null);
            start(async () => {
              const r = await refreshGluconScheduleFromKamiooya();
              if (!r.ok) {
                setErr(r.error || "日程更新に失敗");
                return;
              }
              setMsg(`日程を更新しました（${r.upserted ?? 0}件）`);
              router.refresh();
            });
          }}
        >
          {pending ? "更新中…" : "kamiooya から日程更新"}
        </button>
        <label className="meta" style={{ display: "inline-flex", gap: "0.35rem", alignItems: "center" }}>
          開催日手動
          <input
            type="date"
            value={manualDate}
            onChange={(e) => setManualDate(e.target.value)}
            disabled={pending}
          />
        </label>
        <button
          type="button"
          className="btn"
          disabled={pending || !manualDate}
          onClick={() => {
            setErr(null);
            setMsg(null);
            start(async () => {
              const r = await setManualGluconDate(manualDate);
              if (!r.ok) {
                setErr(r.error || "手動設定に失敗");
                return;
              }
              setMsg(`手動開催日を ${manualDate} に設定（期限 ${r.cycle?.reportDeadline}）`);
              router.refresh();
            });
          }}
        >
          手動反映
        </button>
      </div>
      {err ? <p className="qe-err">{err}</p> : null}
      {msg ? <p className="meta">{msg}</p> : null}
    </section>
  );
}
