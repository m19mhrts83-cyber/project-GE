"use server";

import { createClient } from "@/lib/supabase/server";

export type CmdkSearchHit = {
  id: string;
  kind: "mail" | "watch";
  title: string;
  detail: string;
  href: string;
};

/** ⌘K 検索。直近を取得してクライアント相当の部分一致（個人用途・件数少）。 */
export async function searchCmdk(q: string): Promise<CmdkSearchHit[]> {
  const query = q.trim().slice(0, 80).toLowerCase();
  if (query.length < 1) return [];

  const supabase = await createClient();
  const [{ data: mails }, { data: watches }] = await Promise.all([
    supabase
      .from("triage_items")
      .select("id,subject,partner,from_email,status,lane")
      .neq("kind", "activity")
      .order("received_at", { ascending: false })
      .limit(50),
    supabase
      .from("watch_status")
      .select("id,title,summary,status,level")
      .eq("status", "active")
      .limit(40),
  ]);

  const hits: CmdkSearchHit[] = [];
  for (const m of mails || []) {
    const blob = [m.subject, m.partner, m.from_email, m.lane, m.status]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    if (!blob.includes(query)) continue;
    hits.push({
      id: `mail:${m.id}`,
      kind: "mail",
      title: m.subject || "（件名なし）",
      detail: `${m.partner || m.from_email || "—"} · ${m.status}`,
      href: `/mail/${encodeURIComponent(m.id)}`,
    });
    if (hits.filter((h) => h.kind === "mail").length >= 8) break;
  }
  for (const w of watches || []) {
    const blob = [w.title, w.summary, w.id, w.level]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    if (!blob.includes(query)) continue;
    const href =
      w.id === "zaim_quality"
        ? "/zaim"
        : w.id === "etc_mileage"
          ? "/etc"
          : w.id === "vpoint"
            ? "/vpoint"
            : w.id === "rent_step"
              ? "/rent-step"
              : `/situation#${encodeURIComponent(w.id)}`;
    hits.push({
      id: `watch:${w.id}`,
      kind: "watch",
      title: w.title || String(w.id),
      detail: (w.summary || "").replace(/\s+/g, " ").trim().slice(0, 60),
      href,
    });
    if (hits.filter((h) => h.kind === "watch").length >= 6) break;
  }
  return hits;
}

export async function fetchFirstPartnerPendingId(): Promise<string | null> {
  const supabase = await createClient();
  const { data } = await supabase
    .from("triage_items")
    .select("id")
    .eq("lane", "partner")
    .eq("status", "pending")
    .neq("kind", "activity")
    .order("received_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  return data?.id ?? null;
}
