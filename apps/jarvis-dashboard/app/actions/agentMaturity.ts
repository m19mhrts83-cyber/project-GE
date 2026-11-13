"use server";

/**
 * 成熟度の優先改善を Todoist（AIエージェントチームのレーン）へ「🦾依頼」で入れる。
 * 件名・本文は画面から受け取らず config/agent_maturity.json の固定文から作る。同じ件名のオープンタスクがあれば重複させない。
 */
import { createClient } from "@/lib/supabase/server";
import { maturityConfig } from "@/lib/agentMaturity";
import { createTodoistTask } from "@/lib/todoistTasks";

export type MaturityTaskResult = { ok: true; url: string; duplicate: boolean } | { ok: false; error: string };

export async function addMaturityTask(itemKey: string, actionIndex: number, why: string): Promise<MaturityTaskResult> {
  const auth = await createClient();
  const {
    data: { user },
  } = await auth.auth.getUser();
  if (!user) return { ok: false, error: "ログインが切れています" };

  for (const axis of maturityConfig.axes) {
    const item = axis.items.find((it) => it.key === itemKey);
    if (!item) continue;
    const action = item.actions[Number(actionIndex)];
    if (!action) return { ok: false, error: "改善案が見つかりません" };
    const res = await createTodoistTask("agent_team", {
      title: `[成熟度] ${item.label}：${action}`,
      summary: [
        `${axis.label} ／ ${item.label}`,
        `いまの状態: ${String(why || "").slice(0, 300)}`,
        `世界水準: ${item.world}`,
        "効果は次の週次計測（土曜）でダッシュボードの「成熟度」に出ます。",
      ].join("\n"),
      mark: "requested",
    });
    if (!res.ok) return { ok: false, error: res.error };
    return { ok: true, url: res.url, duplicate: Boolean(res.duplicate) };
  }
  return { ok: false, error: "項目が見つかりません" };
}
