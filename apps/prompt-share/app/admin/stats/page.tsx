"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AdminNav, SiteHeader } from "@/components/SiteChrome";

type StatRow = {
  id: number;
  title: string;
  status: string;
  public_token: string;
  view_count: number;
  generate_count: number;
  copy_count: number;
  events: Record<string, number>;
};

export default function AdminStatsPage() {
  const router = useRouter();
  const [rows, setRows] = useState<StatRow[]>([]);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    (async () => {
      const me = await fetch("/api/auth/me").then((r) => r.json());
      if (!me.user) {
        router.replace("/admin/login");
        return;
      }
      const json = await fetch("/api/admin/stats").then((r) => r.json());
      setRows(json.stats || []);
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
          <h1 className="h1">利用統計</h1>
          <p className="muted">
            チャプロの「出力数」相当は生成（generate）。加えて表示・コピー・外部AI遷移も記録しています。
          </p>
          <div className="card" style={{ overflowX: "auto" }}>
            <table className="table">
              <thead>
                <tr>
                  <th>タイトル</th>
                  <th>表示</th>
                  <th>生成</th>
                  <th>コピー</th>
                  <th>ChatGPT</th>
                  <th>Gemini</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td>
                      {r.title}
                      <div className="muted">{r.status}</div>
                    </td>
                    <td>{r.view_count}</td>
                    <td>{r.generate_count}</td>
                    <td>{r.copy_count}</td>
                    <td>{r.events.open_chatgpt || 0}</td>
                    <td>{r.events.open_gemini || 0}</td>
                    <td>
                      <Link href={`/admin/prompts/${r.id}`}>編集</Link>
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
