"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AdminNav, SiteHeader } from "@/components/SiteChrome";

type Row = {
  id: number;
  title: string;
  status: string;
  public_token: string;
  view_count: number;
  generate_count: number;
  copy_count: number;
  updated_at: string;
};

export default function AdminPromptsPage() {
  const router = useRouter();
  const [rows, setRows] = useState<Row[]>([]);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    (async () => {
      const me = await fetch("/api/auth/me").then((r) => r.json());
      if (!me.user) {
        router.replace("/admin/login");
        return;
      }
      const json = await fetch("/api/admin/prompts").then((r) => r.json());
      setRows(json.prompts || []);
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
          <div className="toolbar">
            <h1 className="h1" style={{ margin: 0 }}>
              プロンプト
            </h1>
            <Link className="btn" href="/admin/prompts/new">
              新規作成
            </Link>
          </div>
          <div className="card" style={{ overflowX: "auto" }}>
            <table className="table">
              <thead>
                <tr>
                  <th>タイトル</th>
                  <th>公開</th>
                  <th>表示</th>
                  <th>生成</th>
                  <th>コピー</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td>{r.title}</td>
                    <td>
                      <span className={`badge ${r.status}`}>{r.status === "published" ? "公開" : "下書き"}</span>
                    </td>
                    <td>{r.view_count}</td>
                    <td>{r.generate_count}</td>
                    <td>{r.copy_count}</td>
                    <td className="row-actions">
                      <Link className="btn secondary" href={`/admin/prompts/${r.id}`}>
                        編集
                      </Link>
                      {r.status === "published" ? (
                        <Link className="btn ghost" href={`/p/${r.public_token}`} target="_blank">
                          公開ページ
                        </Link>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </main>
    </>
  );
}
