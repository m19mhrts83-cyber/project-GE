/**
 * メール要対応 — 見送り学習（mail_action_skip_mute）
 * Slack 投稿除外と Dashboard 未読除外で同じ sync_meta を共有する。
 */
import { createServiceClient } from "@/lib/supabase/admin";
import { parseEmailAddr } from "@/lib/selfEmails";

export const MUTE_META_KEY = "mail_action_skip_mute";
export const DEFAULT_MUTE_THRESHOLD = 2;

export type MuteEntry = {
  skips: number;
  muted: boolean;
  last_at?: string;
  last_subject?: string;
};

export type MuteRegistry = {
  threshold: number;
  entries: Record<string, MuteEntry>;
};

export function muteKeyFromEmail(fromEmail: string | null | undefined): string | null {
  const e = parseEmailAddr(fromEmail) || String(fromEmail || "").trim().toLowerCase();
  if (!e || !e.includes("@")) return null;
  return `from:${e}`;
}

export function emptyMuteRegistry(threshold?: number): MuteRegistry {
  const th = Number(threshold ?? DEFAULT_MUTE_THRESHOLD);
  return {
    threshold: Number.isFinite(th) && th > 0 ? th : DEFAULT_MUTE_THRESHOLD,
    entries: {},
  };
}

/** sync_meta.value（文字列または object）→ MuteRegistry */
export function parseMuteRegistry(raw: unknown, thresholdEnv?: number): MuteRegistry {
  const base = emptyMuteRegistry(
    thresholdEnv ??
      Number(process.env.JARVIS_MAIL_ACTION_MUTE_THRESHOLD || DEFAULT_MUTE_THRESHOLD),
  );
  let obj: Record<string, unknown> | null = null;
  if (typeof raw === "string" && raw.trim()) {
    try {
      obj = JSON.parse(raw) as Record<string, unknown>;
    } catch {
      obj = null;
    }
  } else if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    obj = raw as Record<string, unknown>;
  }
  if (!obj) return base;
  const entries =
    obj.entries && typeof obj.entries === "object" && !Array.isArray(obj.entries)
      ? (obj.entries as Record<string, MuteEntry>)
      : {};
  const th = Number(obj.threshold);
  return {
    threshold: Number.isFinite(th) && th > 0 ? th : base.threshold,
    entries,
  };
}

export function isSenderMutedInRegistry(
  reg: MuteRegistry,
  fromEmail: string | null | undefined,
): boolean {
  const key = muteKeyFromEmail(fromEmail);
  if (!key) return false;
  return Boolean(reg.entries[key]?.muted);
}

/** ミュート済み from アドレス（小文字）の Set */
export function mutedEmailSet(reg: MuteRegistry): Set<string> {
  const out = new Set<string>();
  for (const [key, ent] of Object.entries(reg.entries || {})) {
    if (!ent?.muted) continue;
    const m = key.match(/^from:(.+)$/i);
    if (m?.[1]) out.add(m[1].toLowerCase());
  }
  return out;
}

export function isMutedEmail(
  muted: Set<string>,
  fromEmail: string | null | undefined,
): boolean {
  const addr =
    parseEmailAddr(fromEmail) || String(fromEmail || "").trim().toLowerCase();
  if (!addr) return false;
  return muted.has(addr);
}

export function filterOutMutedSenders<T extends { from_email?: string | null }>(
  rows: T[],
  reg: MuteRegistry,
): T[] {
  const muted = mutedEmailSet(reg);
  if (!muted.size) return rows;
  return rows.filter((r) => !isMutedEmail(muted, r.from_email));
}

export async function loadMuteRegistry(): Promise<MuteRegistry> {
  const base = emptyMuteRegistry(
    Number(process.env.JARVIS_MAIL_ACTION_MUTE_THRESHOLD || DEFAULT_MUTE_THRESHOLD),
  );
  const sb = createServiceClient();
  if (!sb) return base;
  const { data } = await sb
    .from("sync_meta")
    .select("value")
    .eq("key", MUTE_META_KEY)
    .maybeSingle();
  return parseMuteRegistry(data?.value, base.threshold);
}

/** ユーザークライアント等で既に sync_meta を読んでいるとき */
export function muteRegistryFromMetaMap(
  metaMap: Record<string, unknown>,
): MuteRegistry {
  return parseMuteRegistry(metaMap[MUTE_META_KEY]);
}

async function saveMuteRegistry(reg: MuteRegistry): Promise<void> {
  const sb = createServiceClient();
  if (!sb) return;
  const now = new Date().toISOString();
  await sb.from("sync_meta").upsert(
    {
      key: MUTE_META_KEY,
      value: JSON.stringify(reg),
      updated_at: now,
    },
    { onConflict: "key" },
  );
}

/** 見送り連続 streak → 送信者ミュート（Slack / Dashboard 共有）。 */
export async function recordMailSkipLearn(
  fromEmail: string,
  subject: string,
): Promise<{ muted: boolean; skips: number; key: string | null }> {
  const key = muteKeyFromEmail(fromEmail);
  if (!key) return { muted: false, skips: 0, key: null };
  const reg = await loadMuteRegistry();
  const prev = reg.entries[key] || { skips: 0, muted: false };
  const skips = (prev.skips || 0) + 1;
  const muted = skips >= reg.threshold || Boolean(prev.muted);
  reg.entries[key] = {
    skips,
    muted,
    last_at: new Date().toISOString(),
    last_subject: (subject || "").slice(0, 120),
  };
  await saveMuteRegistry(reg);
  return { muted, skips, key };
}

/** 返信／Todoist 成功時に連続カウントをリセット（muted は維持）。 */
export async function resetMailSkipStreak(
  fromEmail: string,
): Promise<{ key: string | null; resets: boolean }> {
  const key = muteKeyFromEmail(fromEmail);
  if (!key) return { key: null, resets: false };
  const reg = await loadMuteRegistry();
  const prev = reg.entries[key];
  if (!prev || (prev.skips || 0) === 0) return { key, resets: false };
  reg.entries[key] = {
    ...prev,
    skips: 0,
    last_at: new Date().toISOString(),
  };
  await saveMuteRegistry(reg);
  return { key, resets: true };
}

export async function isMailSenderMuted(fromEmail: string): Promise<boolean> {
  const reg = await loadMuteRegistry();
  return isSenderMutedInRegistry(reg, fromEmail);
}

/**
 * ミュート済み送信者の残 pending を skipped にする（Dashboard 未読から消す）。
 * 当該 id は呼び出し側で既に更新済みなら excludeId で除外。
 */
export async function skipPendingFromMutedSender(opts: {
  fromEmail: string;
  excludeId?: string;
  source?: string;
}): Promise<number> {
  const key = muteKeyFromEmail(opts.fromEmail);
  if (!key) return 0;
  const addr = key.slice("from:".length);
  const sb = createServiceClient();
  if (!sb) return 0;

  const { data: rows, error } = await sb
    .from("triage_items")
    .select("id,from_email,payload,status")
    .eq("status", "pending")
    .neq("kind", "activity")
    .limit(200);
  if (error || !rows?.length) return 0;

  const now = new Date().toISOString();
  const source = opts.source || "mail_skip_mute";
  let n = 0;
  for (const row of rows) {
    const id = String(row.id || "");
    if (!id || (opts.excludeId && id === opts.excludeId)) continue;
    const rowAddr =
      parseEmailAddr(row.from_email as string) ||
      String(row.from_email || "").trim().toLowerCase();
    if (rowAddr !== addr) continue;
    const payload =
      row.payload && typeof row.payload === "object" && !Array.isArray(row.payload)
        ? { ...(row.payload as Record<string, unknown>) }
        : {};
    payload.mail_skip_mute_auto = { at: now, source, key };
    const { error: uErr } = await sb
      .from("triage_items")
      .update({
        status: "skipped",
        payload,
        updated_at: now,
      })
      .eq("id", id)
      .eq("status", "pending");
    if (!uErr) n += 1;
  }
  return n;
}
