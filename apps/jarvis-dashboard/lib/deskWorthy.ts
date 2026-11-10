/**
 * 判断デスクのカードにする行か（apps/loopware/lib/deskCore.ts の deskWorthy と同じ写し）。
 * ホームの「判断待ち N 件」をデスクの枚数とそろえるために使う。直すときは両方直す。
 */

type Row = {
  lane?: string | null;
  kind?: string | null;
  subject?: string | null;
  from_email?: string | null;
  original_body?: string | null;
  payload?: Record<string, unknown> | null;
};

function obj(x: unknown): Record<string, unknown> {
  return x && typeof x === "object" && !Array.isArray(x) ? (x as Record<string, unknown>) : {};
}

/** 自動送信でも必ず見る（支払いの失敗・引き落としできなかった） */
export const PAY_FAIL_RE =
  /(未済|ご利用いただけませんでした|決済(が)?(失敗|エラー|できませんでした)|お支払い(のご確認|エラー|が確認できません)|引き?落とし(が)?(でき|され)ませんでした|振替不能|残高不足)/;

const BULK_BODY_RE =
  /(配信停止|配信解除|送信専用|返信できません|返信いただいても|ご返信いただいても|unsubscribe|メールマガジン|メルマガ|配信元|受信設定|配信を希望されない|オプトアウト|このメールアドレスは送信のみ)/i;
const REPLY_SUBJECT_RE = /^\s*(re|ｒｅ|返信)\s*[:：]/i;
const BRAND_SUBJECT_RE = /【[^】]{2,40}】/;
const ADDRESSED_RE = /松野\s*(真治)?\s*(様|さま|さん)/;
const FREE_MAIL_RE =
  /@(ezweb\.ne\.jp|docomo\.ne\.jp|softbank\.ne\.jp|i\.softbank\.jp|au\.com|gmail\.com|icloud\.com|me\.com|outlook\.(com|jp)|hotmail\.(com|co\.jp)|yahoo\.co\.jp|ymail\.ne\.jp)$/i;
const ROLE_TOKENS = new Set(
  ("info information support mail noreply no reply notice notification notifications news newsletter team service " +
    "statement post master postmaster campaign matching official customer customers center web mobile welcome invoice " +
    "statements action office account accounts desk admin sales contact direct help system staff member members " +
    "store shop order orders billing press pr marketing").split(" "),
);

function mailAddr(from: string): string {
  const s = String(from || "").trim();
  const m = s.match(/<([^>]+)>/);
  return (m ? m[1] : s).trim().toLowerCase();
}

function looksPersonalLocal(addr: string): boolean {
  const local = addr.split("@")[0].split("+")[0];
  const toks = local.split(/[._-]+/).filter(Boolean);
  if (!toks.length || toks.some((t) => ROLE_TOKENS.has(t) || ROLE_TOKENS.has(t.replace(/\d+$/, "")))) return false;
  return toks.length >= 2 && toks.every((t) => /^[a-z]+$/i.test(t));
}

/** 人が書いたメールか（scripts/jarvis_mail_human.py looks_human_mail と同じ判定） */
export function looksHumanMail(fromEmail: string, subject: string, body: string): boolean {
  const b = String(body || "");
  const subj = String(subject || "");
  if (BULK_BODY_RE.test(b)) return false;
  const addr = mailAddr(fromEmail);
  const addressed = ADDRESSED_RE.test(b.slice(0, 400));
  if (REPLY_SUBJECT_RE.test(subj)) return true;
  if (FREE_MAIL_RE.test(addr)) return true;
  const branded = BRAND_SUBJECT_RE.test(subj);
  if (addressed && !branded) return true;
  if (addressed && looksPersonalLocal(addr)) return true;
  return false;
}

/** 人が判断するカードにするか */
export function deskWorthy(r: Row): boolean {
  const pl = obj(r.payload);
  if (String(r.lane || "") === "partner") return true;
  if (pl.slack_ma_posted_at || pl.loopware_hesitated_at || pl.loopware_miss) return true;
  if (PAY_FAIL_RE.test(String(r.subject || ""))) return true;
  if (String(r.kind || "mail") === "skim") return false;
  // 家族などが携帯・フリーメールから転送してきたもの（転送元の配信停止の文言で落とさない）
  if (/^\s*(fwd?|転送)\s*[:：]/i.test(String(r.subject || "")) && FREE_MAIL_RE.test(mailAddr(String(r.from_email || "")))) return true;
  return looksHumanMail(String(r.from_email || ""), String(r.subject || ""), String(r.original_body || ""));
}
