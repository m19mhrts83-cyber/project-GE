"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { SiteHeader } from "@/components/SiteChrome";

type PromptItem = {
  id: number;
  title: string;
  description: string;
  public_token: string;
  copy_count: number;
  view_count: number;
};

type GroupItem = {
  id: number;
  name: string;
  slug: string;
  description: string;
};

export function PromptListClient({ groupSlug }: { groupSlug?: string }) {
  const [prompts, setPrompts] = useState<PromptItem[]>([]);
  const [groups, setGroups] = useState<GroupItem[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    const q = groupSlug ? `?group=${encodeURIComponent(groupSlug)}` : "";
    Promise.all([
      fetch(`/api/public/prompts${q}`).then((r) => r.json()),
      fetch("/api/public/groups").then((r) => r.json())
    ]).then(([p, g]) => {
      if (p.error) setError(p.error);
      else setPrompts(p.prompts || []);
      setGroups(g.groups || []);
    });
  }, [groupSlug]);

  const currentGroup = groups.find((g) => g.slug === groupSlug);

  return (
    <>
      <SiteHeader />
      <main className="container" style={{ padding: "1.5rem 0 3rem" }}>
        <h1 className="h1">{currentGroup ? currentGroup.name : "公開プロンプト一覧"}</h1>
        <p className="muted">
          {currentGroup
            ? currentGroup.description || "グループ内の公開プロンプト"
            : "URLを知っている方が変数を埋めてコピーし、ChatGPT / Gemini 等で使えます。"}
        </p>

        {!groupSlug && groups.length > 0 ? (
          <section style={{ margin: "1.25rem 0" }}>
            <h2 className="h2">グループ</h2>
            <div className="list-cards">
              {groups.map((g) => (
                <Link key={g.id} href={`/g/${g.slug}`} className="card">
                  <strong>{g.name}</strong>
                  {g.description ? <div className="muted">{g.description}</div> : null}
                </Link>
              ))}
            </div>
          </section>
        ) : null}

        {groupSlug ? (
          <p>
            <Link href="/">← 全一覧へ</Link>
          </p>
        ) : null}

        {error ? <p className="error">{error}</p> : null}
        <section className="list-cards" style={{ marginTop: "1rem" }}>
          {prompts.length === 0 ? (
            <div className="card muted">公開中のプロンプトはまだありません。</div>
          ) : (
            prompts.map((p) => (
              <Link key={p.id} href={`/p/${p.public_token}`} className="card">
                <strong>{p.title}</strong>
                {p.description ? (
                  <div className="muted" style={{ marginTop: 4 }}>
                    {p.description.slice(0, 120)}
                    {p.description.length > 120 ? "…" : ""}
                  </div>
                ) : null}
                <div className="muted" style={{ marginTop: 8, fontSize: "0.85rem" }}>
                  表示 {p.view_count} / コピー {p.copy_count}
                </div>
              </Link>
            ))
          )}
        </section>
      </main>
    </>
  );
}
