"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AdminNav, SiteHeader } from "@/components/SiteChrome";

type Group = {
  id: number;
  name: string;
  slug: string;
  description: string;
  sort_order: number;
  access_level: string;
};

export default function AdminGroupsPage() {
  const router = useRouter();
  const [groups, setGroups] = useState<Group[]>([]);
  const [ready, setReady] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");

  const load = async () => {
    const json = await fetch("/api/admin/groups").then((r) => r.json());
    setGroups(json.groups || []);
  };

  useEffect(() => {
    (async () => {
      const me = await fetch("/api/auth/me").then((r) => r.json());
      if (!me.user) {
        router.replace("/admin/login");
        return;
      }
      await load();
      setReady(true);
    })();
  }, [router]);

  const create = async () => {
    setError("");
    const res = await fetch("/api/admin/groups", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, description })
    });
    const json = await res.json();
    if (!res.ok) {
      setError(json.error || "作成失敗");
      return;
    }
    setName("");
    setDescription("");
    await load();
  };

  const remove = async (id: number) => {
    if (!confirm("グループを削除しますか？（紐づくプロンプトの group_id は null になります）")) return;
    await fetch(`/api/admin/groups/${id}`, { method: "DELETE" });
    await load();
  };

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
          <h1 className="h1">グループ</h1>
          <div className="card" style={{ marginBottom: "1rem" }}>
            <h2 className="h2">新規グループ</h2>
            <div className="field">
              <label>名前</label>
              <input value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="field">
              <label>説明</label>
              <input value={description} onChange={(e) => setDescription(e.target.value)} />
            </div>
            {error ? <p className="error">{error}</p> : null}
            <button className="btn" onClick={create}>
              追加
            </button>
          </div>
          <div className="list-cards">
            {groups.map((g) => (
              <div key={g.id} className="card">
                <strong>{g.name}</strong>
                <div className="muted">slug: {g.slug}</div>
                {g.description ? <div>{g.description}</div> : null}
                <div className="row-actions" style={{ marginTop: 8 }}>
                  <a className="btn secondary" href={`/g/${g.slug}`} target="_blank" rel="noreferrer">
                    公開グループページ
                  </a>
                  <button className="btn ghost" onClick={() => remove(g.id)}>
                    削除
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      </main>
    </>
  );
}
