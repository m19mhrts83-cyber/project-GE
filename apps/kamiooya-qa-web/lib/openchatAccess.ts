// 見られる人を限るLINEオープンチャット（2026-11-18 松野さん「23番は成果達成者限定なので会員全員には表示しない。松野は見たい」）。
// 一覧・検索・AI回答の参考情報のどれにも、スイッチ（qa_feature_flags）で見てよい人にしか出さない。
// 判定はサーバー（semantic-search）だけで行う。画面の絞り込み欄から外すのは見た目の整理で、守りではない。
import {featureAllowed, type FeatureFlag, type FeatureUser} from './featureFlags.ts';

export type RestrictedOpenchat = { feature: string; route_id: string; title_prefix: string };

export const RESTRICTED_OPENCHATS: ReadonlyArray<RestrictedOpenchat> = [
  { feature: 'openchat_23', route_id: '23_saisei_ap_ms_challenge_g', title_prefix: '23再生AP/MS' },
];

type RowLike = { chat_title?: unknown; chat_name?: unknown; route_id?: unknown };

const restrictionOf = (row: RowLike, list: ReadonlyArray<RestrictedOpenchat>) => list.find(r =>
  String(row.route_id ?? '') === r.route_id ||
  String(row.chat_title ?? '').trim().startsWith(r.title_prefix) ||
  String(row.chat_name ?? '').trim().startsWith(r.title_prefix));

export const isRestrictedOpenchat = (row: RowLike) => !!restrictionOf(row, RESTRICTED_OPENCHATS);

/** この人に見せない限定オプチャ。スイッチが読めない・壊れているときは見せない（安全側）。 */
export function hiddenOpenchats(flags: FeatureFlag[] | null, viewer: FeatureUser | null): RestrictedOpenchat[] {
  return RESTRICTED_OPENCHATS.filter(r => {
    const flag = (flags || []).find(f => f.feature === r.feature);
    return !(viewer ? featureAllowed(flag, viewer) : flag?.stage === 'all');
  });
}

export function filterOpenchatRows<T extends RowLike>(rows: T[], hidden: ReadonlyArray<RestrictedOpenchat>): T[] {
  return hidden.length ? rows.filter(row => !restrictionOf(row, hidden)) : rows;
}

/** 本人確認が要るか（会員全員に出ている・誰にも出さないなら、誰かを調べなくても決まる） */
export const needsViewer = (flags: FeatureFlag[] | null) => RESTRICTED_OPENCHATS.some(r => {
  const stage = (flags || []).find(f => f.feature === r.feature)?.stage;
  return stage === 'owner' || stage === 'reviewers';
});

// 添付用のログイン証明（community-attachments の issueSession と同じ形）を確かめて、本人の会員IDを返す。
const encoder = new TextEncoder();
const b64 = (bytes: Uint8Array) => btoa(String.fromCharCode(...bytes)).replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_');
const unb64 = (s: string) => Uint8Array.from(atob(s.replace(/-/g, '+').replace(/_/g, '/')), c => c.charCodeAt(0));
async function hmac(secret: string, value: string): Promise<Uint8Array> {
  const key = await crypto.subtle.importKey('raw', encoder.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  return new Uint8Array(await crypto.subtle.sign('HMAC', key, encoder.encode(value)));
}
export async function sameSecret(a: string, b: string): Promise<boolean> {
  const hash = async (s: string) => new Uint8Array(await crypto.subtle.digest('SHA-256', encoder.encode(s)));
  const [x, y] = await Promise.all([hash(a), hash(b)]);
  return x.reduce((n, v, i) => n | (v ^ y[i]), 0) === 0;
}
export async function viewerFromToken(token: string, secret: string, nowMs: number): Promise<string | null> {
  try {
    if (!token || token.length > 2000 || secret.length < 32) return null;
    const parts = token.split('.');
    if (parts.length !== 2 || !await sameSecret(parts[1], b64(await hmac(secret, parts[0])))) return null;
    const p = JSON.parse(new TextDecoder().decode(unb64(parts[0])));
    if (p.v !== 1 || p.aud !== 'kamiooya-attachments' || !Number.isInteger(p.exp) || p.exp <= nowMs / 1000 ||
      !/^[a-zA-Z0-9_-]{1,100}$/.test(p.uid)) return null;
    return p.uid;
  } catch { return null; }
}
