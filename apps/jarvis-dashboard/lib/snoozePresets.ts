/** スヌーズ起床時刻（JST 想定のローカル Date → ISO） */

export type SnoozePreset = "evening" | "tomorrow_am" | "plus_3d";

export const SNOOZE_PRESET_LABEL: Record<SnoozePreset, string> = {
  evening: "今日 18:00",
  tomorrow_am: "明日 9:00",
  plus_3d: "3日後 9:00",
};

function atLocal(y: number, m: number, d: number, h: number, min = 0): Date {
  return new Date(y, m, d, h, min, 0, 0);
}

/** プリセット → ISO 文字列 */
export function snoozeUntilIso(preset: SnoozePreset, now = new Date()): string {
  const y = now.getFullYear();
  const m = now.getMonth();
  const d = now.getDate();
  if (preset === "evening") {
    let t = atLocal(y, m, d, 18);
    if (t.getTime() <= now.getTime()) {
      t = atLocal(y, m, d + 1, 18);
    }
    return t.toISOString();
  }
  if (preset === "tomorrow_am") {
    return atLocal(y, m, d + 1, 9).toISOString();
  }
  return atLocal(y, m, d + 3, 9).toISOString();
}

export function formatSnoozeUntil(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("ja-JP", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function isSnoozeDue(
  snoozeUntil: string | null | undefined,
  now = new Date(),
): boolean {
  if (!snoozeUntil) return false;
  const t = Date.parse(snoozeUntil);
  return !Number.isNaN(t) && t <= now.getTime();
}
