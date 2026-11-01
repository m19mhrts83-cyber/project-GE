export type WorkEvent = {
  id: string;
  at: string;
  item_id: string;
  kind: string;
  actor: string;
  summary: string;
  minutes: number | null;
  time_kind: "unrecorded" | "owner_confirmed" | "estimated" | "agent_elapsed";
  evidence: string[];
  question_id?: string;
  supersedes?: string;
  work_date?: string;
  status?: string;
};

export type WorkProject = {
  id: string;
  title: string;
  estimate_minutes: number | null;
  items: { id: string; title: string; status: string }[];
  events: WorkEvent[];
};

export type WorkHistory = { version: number; updated_at: string | null; projects: WorkProject[] };

export function parseWorkHistory(raw: unknown): WorkHistory | null {
  if (raw == null) return null;
  const value = typeof raw === "string" ? JSON.parse(raw) : raw;
  if (value?.version !== 1 || !Array.isArray(value.projects)) throw new Error("履歴の形式を確認してください");
  for (const p of value.projects) {
    if (typeof p.id !== "string" || typeof p.title !== "string" || !Array.isArray(p.items) || !Array.isArray(p.events)) throw new Error("案件の形式を確認してください");
    for (const i of p.items) {
      if (typeof i.id !== "string" || typeof i.title !== "string" || typeof i.status !== "string") throw new Error("項目の形式を確認してください");
    }
    for (const e of p.events) {
      if (typeof e.id !== "string" || typeof e.item_id !== "string" || typeof e.summary !== "string" || typeof e.at !== "string" || !Array.isArray(e.evidence)) throw new Error("実行履歴の形式を確認してください");
      if (e.minutes != null && (typeof e.minutes !== "number" || !Number.isFinite(e.minutes) || e.minutes < 0)) throw new Error("作業時間の形式を確認してください");
    }
  }
  return value as WorkHistory;
}

export function workTotals(events: WorkEvent[]) {
  const superseded = new Set(events.map(e => e.supersedes).filter(Boolean));
  const active = events.filter(e => !superseded.has(e.id));
  const total = (kind: WorkEvent["time_kind"]) => active.reduce((n, e) => n + (e.time_kind === kind ? e.minutes ?? 0 : 0), 0);
  return {
    confirmed: total("owner_confirmed"),
    estimated: total("estimated"),
    agent: total("agent_elapsed"),
    unrecorded: active.filter(e => e.minutes == null && e.kind === "log").length,
  };
}

export type WorkEntryInput = {
  projectId: string; itemId: string; eventId: string; summary: string;
  minutes: string; timeKind: string; workDate: string; evidence: string;
  supersedes: string; questionId: string; status: string;
  correctionReason: string;
};

/** 履歴は追記のみ。保存と同時更新制御は呼出側で行う。 */
export function appendWorkEntry(history: WorkHistory, input: WorkEntryInput, now = new Date().toISOString()): WorkHistory {
  const next = structuredClone(history);
  const project = next.projects.find(p => p.id === input.projectId);
  const item = project?.items.find(i => i.id === input.itemId);
  if (!project || !item) throw new Error("案件または作業項目が見つかりません。");
  if (!/^[a-zA-Z0-9_-]{1,100}$/.test(input.eventId)) throw new Error("記録IDが不正です。");
  let summary = input.summary.trim();
  if (!summary || summary.length > 5000) throw new Error("作業内容・訂正理由を1〜5000文字で記入してください。");
  const minutes = input.minutes.trim() === "" ? null : Number(input.minutes);
  if (minutes != null && (!Number.isInteger(minutes) || minutes < 0 || minutes > 1440)) throw new Error("時間は1日分として0〜1440分の整数で入力してください。");
  if (!/^(unrecorded|owner_confirmed|estimated|agent_elapsed)$/.test(input.timeKind)) throw new Error("時間の扱いを選択してください。");
  if (minutes != null && input.timeKind === "unrecorded") throw new Error("時間を入力した場合は、本人確認済み・推計・エージェント処理を選択してください。");
  if (!/^\d{4}-\d{2}-\d{2}$/.test(input.workDate) || Number.isNaN(Date.parse(input.workDate)) || new Date(input.workDate).toISOString().slice(0, 10) !== input.workDate) throw new Error("正しい作業日を指定してください。");
  const evidence = input.evidence.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
  if (evidence.length > 10) throw new Error("根拠リンクは10件までです。");
  for (const link of evidence) {
    let url: URL;
    try { url = new URL(link); } catch { throw new Error("根拠リンクはHTTPSのURLで入力してください。"); }
    if (url.protocol !== "https:" || url.username || url.password || link.length > 2000) throw new Error("根拠リンクは認証情報を含まないHTTPSのURLで入力してください。");
  }
  if (input.supersedes) {
    const reason = input.correctionReason.trim();
    if (!reason || reason.length > 1000) throw new Error("訂正理由を1〜1000文字で記入してください。");
    summary += `\n訂正理由: ${reason}`;
  }
  const existing = project.events.find(e => e.id === input.eventId);
  if (existing) {
    if (existing.summary !== summary || existing.minutes !== minutes || existing.work_date !== input.workDate || existing.supersedes !== (input.supersedes || undefined) || existing.time_kind !== (minutes == null ? "unrecorded" : input.timeKind)) throw new Error("この送信IDは保存済みです。再読み込みして新しい記録として入力してください。");
    return next;
  }
  if (input.supersedes) {
    const old = project.events.find(e => e.id === input.supersedes && e.item_id === item.id);
    if (!old || !["log", "answer"].includes(old.kind)) throw new Error("訂正対象の記録が見つかりません。");
    if (project.events.some(e => e.supersedes === old.id)) throw new Error("この記録は別の操作で訂正済みです。再読み込みして最新の記録を見直してください。");
  }
  if (input.questionId) {
    if (!project.events.some(e => e.id === input.questionId && e.item_id === item.id && e.kind === "ask")) throw new Error("対応する質問が見つかりません。");
    if (project.events.some(e => e.question_id === input.questionId)) throw new Error("この質問は回答済みです。最新の回答から訂正してください。");
  }
  if (input.status && !["planned", "running", "waiting", "done"].includes(input.status)) throw new Error("項目の状態が不正です。");
  project.events.push({
    id: input.eventId, at: now, work_date: input.workDate, item_id: item.id,
    kind: input.questionId ? "answer" : "log", actor: "松野（Dashboard）", summary,
    minutes, time_kind: minutes == null ? "unrecorded" : input.timeKind as WorkEvent["time_kind"], evidence,
    ...(input.supersedes ? { supersedes: input.supersedes } : {}),
    ...(input.questionId ? { question_id: input.questionId } : {}),
    ...(input.status ? { status: input.status } : {}),
  });
  if (input.status) item.status = input.status;
  next.updated_at = now;
  return next;
}
