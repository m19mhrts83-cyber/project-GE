export function toDbId(id: unknown): number {
  const s = String(id ?? "").trim();
  if (!/^\d+$/.test(s)) {
    throw new Error(`Invalid numeric id: ${s}`);
  }
  return Number(s);
}

export function toSessionIdString(id: unknown): string {
  return String(id ?? "").trim();
}

