"use client";

import { useEffect, useState } from "react";

/**
 * どの画面からでも押せる「使い勝手への声」。
 * 使いながら気づいたことを、その画面のまま残す（タグを押すだけでも可）。
 * 相談メモに app_feedback として溜まり、週次で AI が拾って画面を直す材料にする。
 */
const TAGS: { key: string; label: string }[] = [
  { key: "hard_to_see", label: "見づらい" },
  { key: "too_many_steps", label: "手間が多い" },
  { key: "missing_info", label: "欲しい情報がない" },
  { key: "wrong_number", label: "数字がおかしい" },
  { key: "idea", label: "こうしたい" },
  { key: "good", label: "ここは良い" },
];

export default function FeedbackButton({ path }: { path: string }) {
  const [open, setOpen] = useState(false);
  const [tags, setTags] = useState<string[]>([]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  async function send() {
    if (busy || (!tags.length && !note.trim())) return;
    setBusy(true);
    setMsg(null);
    try {
      // 実際に見ている場所（?tab= なども含む）を残す
      const where =
        typeof window !== "undefined" ? window.location.pathname + window.location.search : path;
      const res = await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: where, tags, note }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setMsg(data.error || "残せませんでした");
      } else {
        setTags([]);
        setNote("");
        setMsg("残しました。週次の見直しで拾います。");
        window.setTimeout(() => {
          setOpen(false);
          setMsg(null);
        }, 1400);
      }
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "エラー");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fb-root">
      {open ? (
        <div className="fb-pop" role="dialog" aria-label="この画面への声">
          <div className="dn-kicker">この画面への声</div>
          <div className="fb-title">使っていて気づいたことを、そのまま</div>
          <div className="dn-tags" style={{ marginTop: 10 }}>
            {TAGS.map((t) => (
              <button
                key={t.key}
                type="button"
                className={`dn-chip${tags.includes(t.key) ? " on" : ""}`}
                aria-pressed={tags.includes(t.key)}
                onClick={() =>
                  setTags((c) => (c.includes(t.key) ? c.filter((k) => k !== t.key) : [...c, t.key]))
                }
              >
                {t.label}
              </button>
            ))}
          </div>
          <textarea
            className="dn-input fb-text"
            placeholder="どこが、どうだったら良いか（任意）"
            value={note}
            maxLength={1000}
            rows={3}
            onChange={(e) => setNote(e.target.value)}
          />
          <div className="dn-actions">
            <button type="button" className="dn-cancel" onClick={() => setOpen(false)}>
              閉じる
            </button>
            <button
              type="button"
              className="dn-confirm"
              disabled={busy || (!tags.length && !note.trim())}
              onClick={send}
            >
              {busy ? "送信中…" : "残す"}
            </button>
          </div>
          {msg ? <p className="dn-foot">{msg}</p> : null}
        </div>
      ) : null}
      <button
        type="button"
        className={`fb-fab${open ? " on" : ""}`}
        aria-expanded={open}
        title="この画面の使い勝手について、ひとこと残す"
        onClick={() => setOpen((v) => !v)}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z" />
        </svg>
        <span>声を残す</span>
      </button>
    </div>
  );
}
