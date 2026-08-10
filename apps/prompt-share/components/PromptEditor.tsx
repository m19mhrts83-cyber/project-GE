"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AdminNav, SiteHeader } from "@/components/SiteChrome";
import { PromptPreview } from "@/components/PromptPreview";
import { syncVariablesFromTemplate, type PromptVariable } from "@/lib/prompts";

type Group = { id: number; name: string };

type EditorProps = {
  promptId?: number;
};

export function PromptEditor({ promptId }: EditorProps) {
  const router = useRouter();
  const isNew = !promptId;
  const [ready, setReady] = useState(false);
  const [groups, setGroups] = useState<Group[]>([]);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [template, setTemplate] = useState("");
  const [variables, setVariables] = useState<PromptVariable[]>([]);
  const [groupId, setGroupId] = useState<number | "">("");
  const [status, setStatus] = useState<"draft" | "published">("draft");
  const [accessLevel, setAccessLevel] = useState<"public" | "member">("public");
  const [publicToken, setPublicToken] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [previewValues, setPreviewValues] = useState<Record<string, string>>({});

  useEffect(() => {
    (async () => {
      const me = await fetch("/api/auth/me").then((r) => r.json());
      if (!me.user) {
        router.replace("/admin/login");
        return;
      }
      const g = await fetch("/api/admin/groups").then((r) => r.json());
      setGroups(g.groups || []);
      if (!isNew && promptId) {
        const res = await fetch(`/api/admin/prompts/${promptId}`);
        const json = await res.json();
        if (!res.ok) {
          setError(json.error || "読み込み失敗");
          setReady(true);
          return;
        }
        const p = json.prompt;
        setTitle(p.title || "");
        setDescription(p.description || "");
        setTemplate(p.template || "");
        setVariables(Array.isArray(p.variables) ? p.variables : []);
        setGroupId(p.group_id ?? "");
        setStatus(p.status === "published" ? "published" : "draft");
        setAccessLevel(p.access_level === "member" ? "member" : "public");
        setPublicToken(p.public_token || "");
      }
      setReady(true);
    })();
  }, [isNew, promptId, router]);

  useEffect(() => {
    setVariables((prev) => syncVariablesFromTemplate(template, prev));
  }, [template]);

  useEffect(() => {
    setPreviewValues((prev) => {
      const next: Record<string, string> = {};
      for (const v of variables) next[v.key] = prev[v.key] || "";
      return next;
    });
  }, [variables]);

  const publicUrl = useMemo(() => {
    if (!publicToken || typeof window === "undefined") return "";
    return `${window.location.origin}/p/${publicToken}`;
  }, [publicToken]);

  const save = async (opts?: { regenerate_token?: boolean }) => {
    setSaving(true);
    setError("");
    const payload = {
      title,
      description,
      template,
      variables,
      group_id: groupId === "" ? null : Number(groupId),
      status,
      access_level: accessLevel,
      regenerate_token: opts?.regenerate_token || false
    };
    const res = await fetch(isNew ? "/api/admin/prompts" : `/api/admin/prompts/${promptId}`, {
      method: isNew ? "POST" : "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const json = await res.json();
    setSaving(false);
    if (!res.ok) {
      setError(json.error || "保存に失敗しました");
      return;
    }
    if (isNew) {
      router.push(`/admin/prompts/${json.prompt.id}`);
      return;
    }
    setPublicToken(json.prompt.public_token);
    setVariables(json.prompt.variables || []);
  };

  const remove = async () => {
    if (!promptId || !confirm("このプロンプトを削除しますか？")) return;
    const res = await fetch(`/api/admin/prompts/${promptId}`, { method: "DELETE" });
    if (res.ok) router.push("/admin/prompts");
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
          <div className="toolbar">
            <h1 className="h1" style={{ margin: 0 }}>
              {isNew ? "プロンプト新規作成" : "プロンプト編集"}
            </h1>
            <Link className="btn ghost" href="/admin/prompts">
              一覧へ
            </Link>
          </div>

          <div className="card stack">
            <div className="field">
              <label>タイトル *</label>
              <input value={title} onChange={(e) => setTitle(e.target.value)} />
            </div>
            <div className="field">
              <label>説明</label>
              <textarea value={description} onChange={(e) => setDescription(e.target.value)} />
            </div>
            <div className="field">
              <label>グループ</label>
              <select
                value={groupId === "" ? "" : String(groupId)}
                onChange={(e) => setGroupId(e.target.value ? Number(e.target.value) : "")}
              >
                <option value="">（なし）</option>
                {groups.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>公開状態</label>
              <select value={status} onChange={(e) => setStatus(e.target.value as "draft" | "published")}>
                <option value="draft">下書き</option>
                <option value="published">公開</option>
              </select>
            </div>
            <div className="field">
              <label>アクセスレベル</label>
              <select
                value={accessLevel}
                onChange={(e) => setAccessLevel(e.target.value as "public" | "member")}
              >
                <option value="public">一般公開（URL知っている人）</option>
                <option value="member">神大家メンバー限定（将来）</option>
              </select>
              <div className="help">member は将来フック。現状の公開ページは public のみ表示します。</div>
            </div>
            {!isNew && publicToken ? (
              <div className="field">
                <label>公開URL</label>
                <input readOnly value={publicUrl} />
                <div className="row-actions" style={{ marginTop: 8 }}>
                  <button className="btn secondary" type="button" onClick={() => navigator.clipboard.writeText(publicUrl)}>
                    URLコピー
                  </button>
                  <button className="btn secondary" type="button" onClick={() => save({ regenerate_token: true })}>
                    トークン再発行
                  </button>
                </div>
              </div>
            ) : null}
          </div>

          <div className="grid-2" style={{ marginTop: "1rem" }}>
            <div className="card">
              <h2 className="h2">本文（`{"{変数名}"}` で変数自動抽出）</h2>
              <textarea
                value={template}
                onChange={(e) => setTemplate(e.target.value)}
                style={{ minHeight: 360, width: "100%" }}
              />
              <p className="muted" style={{ fontSize: "0.85rem" }}>
                文字数: {template.length}
              </p>
            </div>
            <div className="card">
              <h2 className="h2">プレビュー</h2>
              <PromptPreview template={template} values={previewValues} variables={variables} />
            </div>
          </div>

          <div className="card" style={{ marginTop: "1rem" }}>
            <h2 className="h2">変数設定</h2>
            {variables.length === 0 ? (
              <p className="muted">本文に {"{変数名}"} を書くとここに現れます。</p>
            ) : (
              variables.map((v, idx) => (
                <div key={v.key} className="card" style={{ marginBottom: "0.75rem", background: "#1a1f33" }}>
                  <strong>
                    {idx + 1}. {v.key}
                  </strong>
                  <div className="field">
                    <label>表示ラベル</label>
                    <input
                      value={v.label}
                      onChange={(e) =>
                        setVariables((prev) =>
                          prev.map((x) => (x.key === v.key ? { ...x, label: e.target.value } : x))
                        )
                      }
                    />
                  </div>
                  <div className="field">
                    <label>プレースホルダー</label>
                    <input
                      value={v.placeholder || ""}
                      onChange={(e) =>
                        setVariables((prev) =>
                          prev.map((x) => (x.key === v.key ? { ...x, placeholder: e.target.value } : x))
                        )
                      }
                    />
                  </div>
                  <div className="field">
                    <label>説明文（入力の補足）</label>
                    <input
                      value={v.help_text || ""}
                      onChange={(e) =>
                        setVariables((prev) =>
                          prev.map((x) => (x.key === v.key ? { ...x, help_text: e.target.value } : x))
                        )
                      }
                    />
                  </div>
                  <div className="field">
                    <label>デフォルト入力例</label>
                    <input
                      value={v.default_example || ""}
                      onChange={(e) =>
                        setVariables((prev) =>
                          prev.map((x) =>
                            x.key === v.key ? { ...x, default_example: e.target.value } : x
                          )
                        )
                      }
                    />
                  </div>
                  <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <input
                      type="checkbox"
                      checked={!!v.required}
                      onChange={(e) =>
                        setVariables((prev) =>
                          prev.map((x) => (x.key === v.key ? { ...x, required: e.target.checked } : x))
                        )
                      }
                    />
                    必須
                  </label>
                </div>
              ))
            )}
          </div>

          {error ? <p className="error">{error}</p> : null}
          <div className="row-actions" style={{ marginTop: "1rem" }}>
            <button className="btn" disabled={saving} onClick={() => save()}>
              {saving ? "保存中…" : "保存"}
            </button>
            {!isNew ? (
              <button className="btn secondary" onClick={remove}>
                削除
              </button>
            ) : null}
          </div>
        </section>
      </main>
    </>
  );
}
