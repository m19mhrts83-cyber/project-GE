"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { SiteHeader } from "@/components/SiteChrome";
import { PromptPreview } from "@/components/PromptPreview";
import { AI_LINKS, fillTemplate, type PromptVariable } from "@/lib/prompts";

type PromptPayload = {
  id: number;
  title: string;
  description: string;
  template: string;
  variables: PromptVariable[];
  public_token: string;
};

export function PublicPromptClient({ token }: { token: string }) {
  const [prompt, setPrompt] = useState<PromptPayload | null>(null);
  const [group, setGroup] = useState<{ name: string; slug: string } | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [filledText, setFilledText] = useState("");
  const [copied, setCopied] = useState(false);
  const [needDefaultConfirm, setNeedDefaultConfirm] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      const res = await fetch(`/api/public/prompts/${token}`);
      const json = await res.json();
      if (cancelled) return;
      if (!res.ok) {
        setError(json.error || "見つかりません");
        setLoading(false);
        return;
      }
      const p = json.prompt as PromptPayload;
      const vars = Array.isArray(p.variables) ? p.variables : [];
      setPrompt({ ...p, variables: vars });
      setGroup(json.group);
      const init: Record<string, string> = {};
      for (const v of vars) init[v.key] = "";
      setValues(init);
      setLoading(false);
      fetch("/api/events", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ public_token: token, event_type: "view" })
      }).catch(() => {});
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const missingRequired = useMemo(() => {
    if (!prompt) return [];
    return prompt.variables.filter((v) => v.required && !(values[v.key] || "").trim());
  }, [prompt, values]);

  const emptyKeys = useMemo(() => {
    if (!prompt) return [];
    return prompt.variables.filter((v) => !(values[v.key] || "").trim());
  }, [prompt, values]);

  const doGenerate = useCallback(async () => {
    if (!prompt) return;
    const text = fillTemplate(prompt.template, values, prompt.variables);
    setFilledText(text);
    setModalOpen(true);
    setCopied(false);
    await fetch("/api/events", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ public_token: token, event_type: "generate" })
    });
  }, [prompt, values, token]);

  const onGenerateClick = () => {
    if (!prompt) return;
    if (missingRequired.length) {
      setError(`必須項目が未入力です: ${missingRequired.map((v) => v.label || v.key).join(", ")}`);
      return;
    }
    setError("");
    if (emptyKeys.length) {
      setNeedDefaultConfirm(true);
      return;
    }
    void doGenerate();
  };

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(filledText);
      setCopied(true);
      await fetch("/api/events", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ public_token: token, event_type: "copy" })
      });
    } catch {
      setError("コピーに失敗しました。全文を選択してコピーしてください。");
    }
  };

  const trackOpen = (event_type: string) => {
    fetch("/api/events", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ public_token: token, event_type })
    }).catch(() => {});
  };

  if (loading) {
    return (
      <>
        <SiteHeader />
        <main className="container" style={{ padding: "2rem 0" }}>
          <p className="muted">読み込み中…</p>
        </main>
      </>
    );
  }

  if (!prompt) {
    return (
      <>
        <SiteHeader />
        <main className="container" style={{ padding: "2rem 0" }}>
          <p className="error">{error || "プロンプトが見つかりません"}</p>
          <Link href="/">一覧へ戻る</Link>
        </main>
      </>
    );
  }

  return (
    <>
      <SiteHeader />
      <main className="container" style={{ padding: "1.5rem 0 3rem" }}>
        <div className="muted" style={{ marginBottom: "0.5rem" }}>
          <Link href="/">一覧</Link>
          {group ? (
            <>
              {" / "}
              <Link href={`/g/${group.slug}`}>{group.name}</Link>
            </>
          ) : null}
        </div>
        <h1 className="h1">{prompt.title}</h1>
        {prompt.description ? (
          <p className="muted" style={{ whiteSpace: "pre-wrap", marginBottom: "1rem" }}>
            {prompt.description}
          </p>
        ) : null}

        <div className="grid-2">
          <section className="card">
            <h2 className="h2">プロンプト本文</h2>
            <p className="muted" style={{ fontSize: "0.85rem", marginTop: 0 }}>
              変数は色付きで表示されます。入力するとリアルタイムで展開されます（テンプレート自体は編集できません）。
            </p>
            <PromptPreview template={prompt.template} values={values} variables={prompt.variables} />
          </section>

          <section className="card">
            <h2 className="h2">変数を入力</h2>
            {prompt.variables.map((v, idx) => (
              <div className="field" key={v.key}>
                <label>
                  <span
                    style={{
                      display: "inline-block",
                      background: ["#fef08a", "#fbcfe8", "#bbf7d0", "#bfdbfe", "#ddd6fe", "#fed7aa"][
                        idx % 6
                      ],
                      color: "#111827",
                      padding: "0.05rem 0.4rem",
                      borderRadius: 6,
                      marginRight: 6,
                      fontWeight: 700,
                      fontSize: "0.85rem"
                    }}
                  >
                    {v.label || v.key}
                  </span>
                  {v.required ? <span className="error">*</span> : null}
                </label>
                <textarea
                  placeholder={v.placeholder || v.default_example || `${v.label || v.key}を入力`}
                  value={values[v.key] || ""}
                  onChange={(e) => setValues((prev) => ({ ...prev, [v.key]: e.target.value }))}
                  rows={v.key.includes("出力") || v.key.includes("要約") ? 6 : 3}
                />
                {v.help_text ? <div className="help">{v.help_text}</div> : null}
                {!v.help_text && v.default_example ? (
                  <div className="help">未入力時の例: {v.default_example}</div>
                ) : null}
              </div>
            ))}
            {error ? <p className="error">{error}</p> : null}
            <button className="btn" style={{ width: "100%" }} onClick={onGenerateClick}>
              プロンプトを生成
            </button>
          </section>
        </div>
      </main>

      {needDefaultConfirm ? (
        <div className="modal-backdrop">
          <div className="modal">
            <h2 className="h2">未入力の回答</h2>
            <p>未入力の箇所にはデフォルトの入力例が入ります。</p>
            <div className="row-actions" style={{ marginTop: "1rem" }}>
              <button
                className="btn"
                onClick={() => {
                  setNeedDefaultConfirm(false);
                  void doGenerate();
                }}
              >
                了解しました
              </button>
              <button className="btn secondary" onClick={() => setNeedDefaultConfirm(false)}>
                戻る
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {modalOpen ? (
        <div className="modal-backdrop">
          <div className="modal">
            <div className="toolbar">
              <h2 className="h2" style={{ margin: 0 }}>
                完成プロンプト
              </h2>
              <button className="btn ghost" onClick={() => setModalOpen(false)}>
                閉じる
              </button>
            </div>
            <textarea readOnly value={filledText} style={{ width: "100%", minHeight: 280 }} />
            <div className="row-actions" style={{ marginTop: "0.75rem" }}>
              <button className="btn" onClick={onCopy}>
                {copied ? "コピーしました" : "コピー"}
              </button>
            </div>
            <p className="muted" style={{ marginTop: "1rem", marginBottom: "0.35rem" }}>
              コピー後、外部AIへ貼り付けてください
            </p>
            <div className="ai-links">
              {AI_LINKS.map((l) => (
                <a
                  key={l.key}
                  className="btn secondary"
                  href={l.href}
                  target="_blank"
                  rel="noreferrer"
                  onClick={() => trackOpen(l.key)}
                >
                  {l.label}
                </a>
              ))}
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
