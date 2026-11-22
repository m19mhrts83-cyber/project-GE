import { createServiceClient } from "@/lib/supabase/admin";
import { createTodoistTask } from "@/lib/todoistTasks";
import { logOwnerDecision } from "@/lib/ownerDecisionLog";
import { MEETING_TODO_PREFIX, type MeetingDeps } from "@/lib/meetingTodoAction";

async function notify(kind: "REPORT" | "OPS", text: string) {
  const url = process.env[`SLACK_WEBHOOK_AI_TEAM_${kind}`];
  if (!url) throw new Error("Slack notification not configured");
  const r=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text})});
  if (!r.ok) throw new Error("Slack notification failed");
}
export function meetingTodoDeps(source: string): MeetingDeps {
  const sb=createServiceClient();
  const versions=new Map<string,{raw:string;stamp:string}>();
  return {
    async read(id) {
      if (!sb) throw new Error("candidate store missing");
      const r=await sb.from("sync_meta").select("value,updated_at").eq("key",MEETING_TODO_PREFIX+id).maybeSingle();
      if (r.error) throw new Error("candidate read failed");
      if (r.data?.value) versions.set(id,{raw:r.data.value,stamp:r.data.updated_at});
      return r.data?.value ?? null;
    },
    async cas(id,old,row) {
      if (!sb) throw new Error("candidate store missing");
      const prior=versions.get(id);
      if (!prior || prior.raw!==old) return false;
      const stamp=new Date(Math.max(Date.now(),Date.parse(prior.stamp)+1)).toISOString();
      const raw=JSON.stringify(row);
      const r=await sb.from("sync_meta").update({value:raw,updated_at:stamp})
        .eq("key",MEETING_TODO_PREFIX+id).eq("updated_at",prior.stamp).select("key");
      if (r.error) throw new Error("candidate update failed");
      const changed=r.data?.length === 1;
      if (changed) versions.set(id,{raw,stamp});
      return changed;
    },
    create(row) {
      return createTodoistTask(row.lane,{title:row.title,mark:"requested",strictDedupe:true,
        due:row.due_date || undefined,labels:["SecondBrain","quick"],
        summary:`candidate_id=${row.candidate_id}\nmeeting_id=${row.meeting_id}\n出典: ${row.notion_url}\n担当: ${row.assignee}\n期限原文: ${row.due_raw || "未定"}`});
    },
    async finish(row,action) {
      if (action === "create") {
        const token=process.env.TODOIST_API_TOKEN;
        if (!token || !row.task_id) throw new Error("task/token missing");
        const r=await fetch("https://api.todoist.com/api/v1/comments",{method:"POST",
          headers:{Authorization:`Bearer ${token}`,"Content-Type":"application/json"},
          body:JSON.stringify({task_id:row.task_id,content:`【チャッピー】\nサマリ: 会議の本人担当TODOを個別了承後に起票\n出典: ${row.notion_url}\nmeeting_id: ${row.meeting_id}\ncandidate_id: ${row.candidate_id}\n担当根拠: ${row.evidence}\n期限原文: ${row.due_raw || "未定"}`})});
        if (!r.ok) throw new Error("source comment failed");
      }
      // Require durable decision recording here; the legacy helper is soft-fail by design.
      const decisionKey=`meeting714:${row.candidate_id}:${action}`;
      await logOwnerDecision({surface:"todoist_312",source,employee:"312",action,
        targetType:"meeting_todo",targetId:row.candidate_id,subject:row.title,idemKey:decisionKey,
        payload:{candidate_id:row.candidate_id,meeting_id:row.meeting_id,notion_url:row.notion_url,task_id:row.task_id || null}});
      if (!sb) throw new Error("decision store missing");
      const check=await sb.from("owner_decisions").select("id").eq("payload->>idem_key",decisionKey).limit(1);
      if (check.error || !check.data?.length) throw new Error("decision recording failed");
      if (action === "create") await notify("REPORT",`【報告】312 Todoist起票整理\n会議候補1件を登録しました。\n${row.task_url}`);
    },
    async fail(id,reason) { await notify("OPS",`【ops】312 Todoist起票整理\n${reason}\n候補ID: ${id}`); },
  };
}
