import Link from "next/link";
import { notFound } from "next/navigation";
import Shell from "@/components/Shell";
import CopyPathButton from "@/components/CopyPathButton";
import FolderLinks from "@/components/FolderLinks";
import {
  getFolderLinksMany,
  openchatFolderKey,
  partnerFolderKey,
} from "@/lib/folderLinks";
import {
  parseOpenchatDigest,
  yoritooriCursorPrompt,
  yoritooriRelPath,
} from "@/lib/openchatDigest";
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

  const { data: meta } = await supabase.from("sync_meta").select("key,value");
  const metaMap = Object.fromEntries((meta || []).map((m) => [m.key, m.value]));
  const digest = parseOpenchatDigest(metaMap.openchat_digest);
  const digestGroup = (digest?.groups || []).find(
    (g) =>
      g.slug === raw ||
      encodeURIComponent(g.name.replace(/\s+/g, "_")) === raw ||
      candidates.includes(g.name),
  );

  const matched = (activities || []).filter((a) => {
    const p = (a.partner || "").trim();
    return candidates.some(
      (c) =>
        c === p || encodeURIComponent(p.replace(/\s+/g, "_")) === raw,
    );
  });

  const bySlug = (activities || []).filter((a) => {
    const p = (a.partner || "").trim();
    return encodeURIComponent(p.replace(/\s+/g, "_")) === raw;
  });
  const rows = bySlug.length ? bySlug : matched;
  const displayName = rows[0]?.partner || digestGroup?.name || name;
  if (!rows.length && !digestGroup && !displayName) notFound();

  const path = yoritooriRelPath(displayName);
  const prompt = yoritooriCursorPrompt(displayName);
  const folderLinks = getFolderLinksMany([
    openchatFolderKey(displayName),
    partnerFolderKey("815_神大家オプチャ", null),
  ]);

  return (
    <Shell active="/openchat">
      <p className="back">
        <Link href="/openchat">← オプチャ一覧</Link>
      </p>
      <h1>{displayName}</h1>
      <p className="sub">
        情報収集枠。返信提案なし。iPhone／Web
        ではこのページが本文確認の正。Mac ではパスコピーか Cursor
        プロンプトで OneDrive のやり取り MD を開く。
      </p>
      <FolderLinks links={folderLinks} />
      <p className="openchat-group-actions">
        <CopyPathButton path={path} label="やり取りパスをコピー" />
        <span className="meta"> · </span>
        <CopyPathButton path={prompt} label="Cursorプロンプト" />
      </p>
      <p className="meta openchat-path-hint">{path}</p>

      {digestGroup?.lines?.length ? (
        <section className="openchat-health level-info" aria-label="有益要約">
          <h2 style={{ margin: "0 0 8px", fontSize: "1.05rem" }}>有益要約</h2>
          <ul className="openchat-group-lines">
            {digestGroup.lines.slice(0, 3).map((ln, i) => (
              <li key={i}>{ln}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <h2>直近更新</h2>
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
