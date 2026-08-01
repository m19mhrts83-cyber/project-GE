import Link from "next/link";
import { notFound } from "next/navigation";
import Shell from "@/components/Shell";
import CopyPathButton from "@/components/CopyPathButton";
import { yoritooriRelPath } from "@/lib/openchatDigest";
import { createClient } from "@/lib/supabase/server";

export default async function OpenchatGroupPage({
  params,
}: {
  params: Promise<{ group: string }>;
}) {
  const { group: raw } = await params;
  let name = raw;
  try {
    name = decodeURIComponent(raw).replace(/_/g, " ");
  } catch {
    name = raw;
  }
  // slug used encodeURIComponent of name with spaces→_ ; try both
  const candidates = [
    name,
    decodeURIComponent(raw),
    raw.replace(/_/g, " "),
  ];

  const supabase = await createClient();
  const { data: activities } = await supabase
    .from("triage_items")
    .select("*")
    .eq("lane", "openchat")
    .eq("kind", "activity")
    .order("received_at", { ascending: false })
    .limit(200);

  const matched = (activities || []).filter((a) => {
    const p = (a.partner || "").trim();
    return candidates.some((c) => c === p || encodeURIComponent(p.replace(/\s+/g, "_")) === raw);
  });

  // If URL slug is exact partner with underscores as spaces
  const bySlug = (activities || []).filter((a) => {
    const p = (a.partner || "").trim();
    return encodeURIComponent(p.replace(/\s+/g, "_")) === raw;
  });
  const rows = bySlug.length ? bySlug : matched;
  const displayName = rows[0]?.partner || name;
  if (!rows.length && !displayName) notFound();

  const path = yoritooriRelPath(displayName);

  return (
    <Shell active="/openchat">
      <p className="back">
        <Link href="/openchat">← オプチャ一覧</Link>
      </p>
      <h1>{displayName}</h1>
      <p className="sub">
        情報収集枠。返信提案なし。全文は OneDrive のやり取り MD。
      </p>
      <p className="openchat-group-actions">
        <CopyPathButton path={path} label="やり取りパスをコピー" />
        <span className="meta"> · {path}</span>
      </p>

      {!rows.length ? (
        <p className="empty">このグループの直近 activity はありません</p>
      ) : (
        rows.map((it) => (
          <article key={it.id} className="card">
            <header>
              <span className="lvl">{it.channel || "更新"}</span>
              <strong>{it.subject || "（件名なし）"}</strong>
              <span className="meta">{it.received_at}</span>
            </header>
            <p className="sum">{it.summary}</p>
          </article>
        ))
      )}
    </Shell>
  );
}
