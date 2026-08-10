"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AdminNav, SiteHeader } from "@/components/SiteChrome";

export default function AdminDashboardPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [counts, setCounts] = useState({ prompts: 0, published: 0, groups: 0, copies: 0 });

  useEffect(() => {
    (async () => {
      const me = await fetch("/api/auth/me").then((r) => r.json());
      if (!me.user) {
        router.replace("/admin/login");
        return;
      }
      const [p, g] = await Promise.all([
        fetch("/api/admin/prompts").then((r) => r.json()),
        fetch("/api/admin/groups").then((r) => r.json())
      ]);
      const prompts = p.prompts || [];
      setCounts({
        prompts: prompts.length,
        published: prompts.filter((x: { status: string }) => x.status === "published").length,
        groups: (g.groups || []).length,
        copies: prompts.reduce((s: number, x: { copy_count: number }) => s + Number(x.copy_count || 0), 0)
      });
      setReady(true);
    })();
  }, [router]);

  if (!ready) {
    return (
      <>
        <SiteHeader admin />
        <main className="container" style={{ padding: "2rem 0" }}>
          <p className="muted">読み込み中…</p>
        </main>
      </>
    );
  }

  return (
    <>
      <SiteHeader admin />
      <main className="container admin-shell">
        <AdminNav />
        <section>
          <h1 className="h1">管理ダッシュボード</h1>
          <div className="list-cards">
            <div className="card">プロンプト総数: <strong>{counts.prompts}</strong></div>
            <div className="card">公開中: <strong>{counts.published}</strong></div>
            <div className="card">グループ: <strong>{counts.groups}</strong></div>
            <div className="card">累計コピー: <strong>{counts.copies}</strong></div>
          </div>
          <div className="row-actions" style={{ marginTop: "1rem" }}>
            <Link className="btn" href="/admin/prompts/new">
              新規プロンプト
            </Link>
            <Link className="btn secondary" href="/admin/prompts">
              プロンプト一覧
            </Link>
          </div>
        </section>
      </main>
    </>
  );
}
