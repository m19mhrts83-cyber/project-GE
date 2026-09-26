/** Genspark Meeting Notes via tool_cli HTTP (same as gsk meeting). */

const GSK_BASE = (process.env.GSK_BASE_URL || "https://www.genspark.ai").replace(/\/$/, "");

export type MeetingNoteBrief = {
  id?: string;
  title?: string;
  status?: string;
  created_at?: string;
  duration_human?: string;
  duration_seconds?: number;
};

export type MeetingNoteDetail = MeetingNoteBrief & {
  summary?: string;
};

function apiKey(): string {
  return (process.env.GSK_API_KEY || "").trim();
}

async function meetingCall(body: Record<string, unknown>): Promise<Record<string, unknown>> {
  const key = apiKey();
  if (!key) {
    throw new Error("GSK_API_KEY 未設定");
  }
  const res = await fetch(`${GSK_BASE}/api/tool_cli/meeting`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Api-Key": key,
      "X-GSK-CLI-Version": "jarvis-dashboard-advisor-pack",
    },
    body: JSON.stringify(body),
  });
  const text = await res.text();
  if (!res.ok) {
    throw new Error(`Genspark meeting HTTP ${res.status}: ${text.slice(0, 300)}`);
  }
  return JSON.parse(text) as Record<string, unknown>;
}

export async function listMeetings(pageSize = 50, continuationToken?: string) {
  const payload: Record<string, unknown> = { action: "list", page_size: pageSize };
  if (continuationToken) payload.continuation_token = continuationToken;
  const raw = await meetingCall(payload);
  const data = (raw.data as Record<string, unknown>) || {};
  const notes = Array.isArray(data.notes) ? (data.notes as MeetingNoteBrief[]) : [];
  return {
    notes,
    has_more: Boolean(data.has_more),
    continuation_token: (data.continuation_token as string) || undefined,
  };
}

export async function getMeetingSummary(taskId: string): Promise<MeetingNoteDetail> {
  const raw = await meetingCall({
    action: "get",
    task_id: taskId,
    detail_level: "summary",
  });
  const data = (raw.data as Record<string, unknown>) || raw;
  return {
    id: String(data.id || data.task_id || taskId),
    title: data.title as string | undefined,
    status: data.status as string | undefined,
    created_at: data.created_at as string | undefined,
    duration_human: data.duration_human as string | undefined,
    summary: String(data.summary || data.ai_summary || ""),
  };
}

/** 金締土〜金のノートを list から集め、summary を付与（最大40）。 */
export async function fetchKinshuMeetingSummaries(
  startIso: string,
  endIso: string,
): Promise<{ notes: MeetingNoteDetail[]; error?: string }> {
  try {
    const start = startIso;
    const end = endIso;
    const collected: MeetingNoteBrief[] = [];
    let token: string | undefined;
    for (let page = 0; page < 8; page++) {
      const batch = await listMeetings(50, token);
      let hitOlder = false;
      for (const n of batch.notes) {
        const created = (n.created_at || "").slice(0, 10);
        if (!created) continue;
        if (created >= start && created <= end) {
          collected.push(n);
        } else if (created < start) {
          hitOlder = true;
        }
      }
      if (hitOlder || !batch.has_more || !batch.continuation_token) break;
      token = batch.continuation_token;
      if (collected.length >= 80) break;
    }

    const notes: MeetingNoteDetail[] = [];
    for (const n of collected.slice(0, 40)) {
      if (!n.id) continue;
      try {
        const det = await getMeetingSummary(n.id);
        notes.push({
          ...n,
          ...det,
          summary: (det.summary || "").slice(0, 1200),
        });
      } catch (e) {
        notes.push({
          ...n,
          summary: `(summary取得失敗: ${e instanceof Error ? e.message : String(e)})`,
        });
      }
    }
    return { notes };
  } catch (e) {
    return { notes: [], error: e instanceof Error ? e.message : String(e) };
  }
}
