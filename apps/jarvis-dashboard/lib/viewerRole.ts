/**
 * 見る専用ロール（viewer）。2026-11-27
 *
 * 付け方: Supabase ユーザーの app_metadata.role = "viewer"。
 * app_metadata は本人が書き換えられない（service_role / 管理 API のみ）。user_metadata は本人が書けるので使わない。
 * 強制は2層: ① middleware（全ページ・サーバーアクション・API の書き込みメソッドを 403）
 *            ② Supabase RLS（20261127_viewer_readonly_rls.sql。anon キー＋JWT で直接書く抜け道を塞ぐ）
 */

export const VIEWER_ROLE = "viewer";

type UserLike = { app_metadata?: Record<string, unknown> | null } | null | undefined;

export function isViewerUser(user: UserLike): boolean {
  return String(user?.app_metadata?.role ?? "").trim().toLowerCase() === VIEWER_ROLE;
}

const READ_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

/** viewer がサインアウトだけはできるようにする（POST） */
const VIEWER_WRITE_ALLOW_PATHS = new Set(["/auth/signout"]);

/** viewer のリクエストを通してよいか。読み取りメソッドと許可パス以外は拒否（サーバーアクションも POST なのでここで止まる） */
export function viewerMayRequest(method: string, path: string): boolean {
  if (READ_METHODS.has(String(method).toUpperCase())) return true;
  return String(method).toUpperCase() === "POST" && VIEWER_WRITE_ALLOW_PATHS.has(path);
}
