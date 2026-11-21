/** Saved 714 candidates only. Existing sync_meta, CAS by the version read with the serialized value. */
export const MEETING_TODO_PREFIX = "meeting_todo:v1:";
export type MeetingCandidate = {
  candidate_id: string; meeting_id: string; todo: string; title: string; lane: string;
  owner_confirmed: boolean; extracted: boolean; notion_page_id: string; notion_url: string;
  assignee: string; evidence: string; due_date?: string | null; due_raw?: string;
  status: string; task_id?: string; task_url?: string; finished?: boolean;
  [key: string]: unknown;
};
type Result = { ok: boolean; message: string };
export type MeetingDeps = {
  read: (id: string) => Promise<string | null>;
  cas: (id: string, old: string, row: MeetingCandidate) => Promise<boolean>;
  create: (row: MeetingCandidate) => Promise<{ok:true;id:string;url:string} | {ok:false;error:string}>;
  finish: (row: MeetingCandidate, action: "create" | "dismiss") => Promise<void>;
  fail: (id: string, reason: string) => Promise<void>;
};
export async function applyMeetingTodo(id: string, action: "create" | "dismiss", d: MeetingDeps): Promise<Result> {
  if (!/^[a-f0-9]{64}$/.test(id)) return {ok:false,message:"候補IDが不正です"};
  try {
    const raw = await d.read(id);
    if (!raw) return {ok:false,message:"候補が見つかりません"};
    const row = JSON.parse(raw) as MeetingCandidate;
    if (row.candidate_id !== id || !row.owner_confirmed || !row.extracted || !row.notion_page_id ||
        !/^https:\/\//.test(row.notion_url || "") || !row.meeting_id || !row.evidence) {
      return {ok:false,message:"Notion保存・本人担当の確認が必要です"};
    }
    if (row.status === "dismissed") return {ok:true,message:"見送り済みです（再提案しません）"};
    if (row.status === "created" && row.finished) return {ok:true,message:`登録済みです\n${row.task_url}`};
    if (!["posted","posting","created"].includes(row.status)) return {ok:false,message:"処理中または要照合です。再登録しません"};
    // A subsequent dismiss must never suppress postprocessing of an already-created task.
    if (row.status === "created" && action === "dismiss") return {ok:false,message:"登録済みです。見送りへ変更できません"};
    const claimed: MeetingCandidate = {...row,status:row.status === "created" ? "finishing" : action === "dismiss" ? "dismissed" : "creating"};
    if (!await d.cas(id,raw,claimed)) return {ok:false,message:"別の操作で処理中です"};
    let current = claimed;
    if (action === "create" && !row.task_id) {
      let result;
      try { result = await d.create(row); }
      catch { result = {ok:false as const,error:"Todoistの結果が不明です（再送せず照合）"}; }
      if (!result.ok) {
        const failed = {...current,status:"uncertain",error:result.error};
        await d.cas(id,JSON.stringify(current),failed);
        await d.fail(id,"Todoist作成または重複照合に失敗。再送せず照合してください");
        return {ok:false,message:"起票できませんでした。状態照合が必要です"};
      }
      const created: MeetingCandidate = {...current,status:"finishing",task_id:result.id,task_url:result.url};
      if (!await d.cas(id,JSON.stringify(current),created)) {
        await d.fail(id,"Todoist作成後の結果保存に失敗。再作成禁止");
        return {ok:false,message:`Todoist処理済み・記録要確認\n${result.url}`};
      }
      current = created;
    }
    // Durable task_id exists before comments/logging/notifications. Failure never recreates a task.
    try {
      await d.finish(current,action);
    } catch {
      await d.fail(id,"判断履歴・コメント・通知の一部に失敗。タスクは再作成しません");
      // Keep finishing/dismissed: uncertain side effects are reconciled, not blindly retried.
      return {ok:false,message:"判断反映済み・出典または通知の記録要確認（再起票しません）"};
    }
    const done = {...current,status:action === "create" ? "created" : "dismissed",finished:true};
    if (!await d.cas(id,JSON.stringify(current),done)) {
      await d.fail(id,"結果確定の記録に失敗。再作成禁止");
      return {ok:false,message:"結果の記録要確認です（再起票しません）"};
    }
    return {ok:true,message:action === "create" ? `起票しました\n${done.task_url}` : "見送りました（再提案しません）"};
  } catch {
    await d.fail(id,"候補台帳に接続できません。処理を停止しました").catch(()=>{});
    return {ok:false,message:"候補台帳を確認できないため処理を停止しました"};
  }
}
