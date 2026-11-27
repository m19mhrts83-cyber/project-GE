/**
 * 判断を「押した人のアカウント」を判断ログに残すための小さな部品（外部依存なし）。
 * ユーザーID（Supabase auth の id）だけを使う。メールアドレスは入れない。
 * 取れない時は何も足さない（従来どおり）。
 */

/** Supabase の auth.getUser() の結果から、ユーザーIDだけを取り出す */
export function actorIdFromAuth(
  res: { data?: { user?: { id?: unknown } | null } | null } | null | undefined,
): string | null {
  const id = res?.data?.user?.id;
  return typeof id === "string" && id.trim() ? id.trim().slice(0, 80) : null;
}

/** payload に actor_id を足した新しい payload を返す（取れない時はそのまま） */
export function withActorId<T extends Record<string, unknown>>(payload: T, actorId: string | null): T {
  if (!actorId) return payload;
  return { ...payload, actor_id: actorId };
}

/** サーバーアクション内で呼ぶ。失敗しても本線は止めない */
export async function currentActorId(supabase: {
  auth: { getUser: () => Promise<{ data?: { user?: { id?: unknown } | null } | null }> };
}): Promise<string | null> {
  try {
    return actorIdFromAuth(await supabase.auth.getUser());
  } catch {
    return null;
  }
}
