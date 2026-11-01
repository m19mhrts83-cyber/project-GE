"use client";

import { useActionState, useEffect, useState } from "react";
import { saveKamiooyaHistory } from "@/app/actions/kamiooyaHistory";
import type { WorkEvent } from "@/lib/kamiooyaWorkHistory";

export default function KamiooyaHistoryForm({ projectId, itemId, initialId, workDate, previous, questionId }: {
  projectId: string; itemId: string; initialId: string; workDate: string; previous?: WorkEvent; questionId?: string;
}) {
  const [state, action, pending] = useActionState(saveKamiooyaHistory, { ok: false, message: "" });
  const [eventId, setEventId] = useState(initialId);
  useEffect(() => { if (state.savedId) setEventId(crypto.randomUUID()); }, [state.savedId]);
  const label = previous ? "時間・記録を見直す" : questionId ? "この質問に回答する" : "作業記録を追加する";
  return <details style={{ margin: "12px 0", borderTop: "1px solid var(--border, #ddd)", paddingTop: 10 }}>
    <summary style={{ cursor: "pointer" }}>{label}</summary>
    <form action={action} style={{ display: "grid", gap: 10, marginTop: 12 }}>
      <input type="hidden" name="projectId" value={projectId} />
      <input type="hidden" name="itemId" value={itemId} />
      <input type="hidden" name="eventId" value={eventId} />
      <input type="hidden" name="supersedes" value={previous?.id ?? ""} />
      <input type="hidden" name="questionId" value={questionId ?? ""} />
      <label>作業日 <input type="date" name="workDate" defaultValue={previous?.work_date ?? workDate} required /></label>
      <label>{questionId ? "回答内容" : "作業内容・結果"}
        <textarea name="summary" rows={3} maxLength={5000} required defaultValue={previous?.summary ?? ""} style={{ width: "100%", boxSizing: "border-box" }} />
      </label>
      {previous ? <label>訂正理由 <input name="correctionReason" required maxLength={1000} placeholder="例：本人確認で20分に修正" /></label> : null}
      <label>作業時間（分・不明なら空欄） <input name="minutes" type="number" min="0" max="1440" step="1" defaultValue={previous?.minutes ?? ""} /></label>
      <label>時間の扱い <select name="timeKind" defaultValue={previous && previous.time_kind !== "unrecorded" ? previous.time_kind : "owner_confirmed"}>
        <option value="owner_confirmed">本人の作業時間（確認済み）</option>
        <option value="estimated">推計時間</option>
        <option value="agent_elapsed">エージェントの処理時間</option>
        <option value="unrecorded">時間未記録</option>
      </select></label>
      <label>項目の状態 <select name="status" defaultValue=""><option value="">変更しない</option><option value="planned">予定</option><option value="running">作業中</option><option value="waiting">確認待ち</option><option value="done">完了</option></select></label>
      <label>根拠・成果物リンク（任意・1行1件）<textarea name="evidence" rows={2} defaultValue={previous?.evidence.join("\n") ?? ""} style={{ width: "100%", boxSizing: "border-box" }} /></label>
      {previous ? <p className="meta">元の記録を残して訂正を追加します。時間の集計は訂正後だけを数えます。</p> : null}
      <button className="btn" type="submit" disabled={pending}>{pending ? "保存中…" : "履歴に保存"}</button>
      {state.message ? <p role={state.ok ? "status" : "alert"}>{state.message}</p> : null}
    </form>
  </details>;
}
