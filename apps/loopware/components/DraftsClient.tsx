"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Icon from "@/components/Icon";

type Item = { id: string; caseName: string; recipient: string; channel: string; status: string; updatedAt: string; versions: number };

const CHANNELS = [
  ["chatwork", "Chatwork"],
  ["mail", "メール"],
  ["line", "LINE"],
  ["slack", "Slack"],
  ["doc", "文書"],
  ["other", "その他"],
] as const;

/** 下書きの一覧と、貼り付けて始める */
export default function DraftsClient() {
  const [items, setItems] = useState<Item[] | null>(null);
  const [err, setErr] = useState("");
  const [form, setForm] = useState({ caseName: "", recipient: "", channel: "chatwork", text: "" });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetch("/api/drafts", { cache: "no-store" })
      .then((r) => r.json())
      .then((j) => (j.ok ? setItems(j.items) : setErr(j.error || "読み込めません")))
      .catch(() => setErr("通信できませんでした"));
  }, []);

  async function create() {
    setBusy(true);
    setErr("");
    try {
      const r = await fetch("/api/drafts", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(form) });
      const j = await r.json();
      if (!j.ok) setErr(j.error || "作れませんでした");
      else location.href = `/drafts/${j.id}`;
    } catch {
      setErr("通信できませんでした");
    } finally {
      setBusy(false);
    }
  }

  const open = (items || []).filter((i) => i.status === "open");
  const done = (items || []).filter((i) => i.status === "done").slice(0, 10);

  return (
    <div className="list">
      <div className="eyebrow">直し中</div>
      {items === null && !err ? <div className="card meta">読み込み中…</div> : null}
      {items && !open.length ? <div className="card meta">直し中の下書きはありません</div> : null}
      {open.map((i) => (
        <Link key={i.id} className="glass nav-card" href={`/drafts/${i.id}`}>
          <span className="ico">
            <Icon name="mic" size={22} />
          </span>
          <span className="txt">
            <strong>{i.caseName}</strong>
            <span className="meta">
              {i.recipient}・{i.channel}・{i.versions}版
            </span>
          </span>
          <Icon name="next" size={18} />
        </Link>
      ))}

      <details className="card">
        <summary>
          <strong>貼り付けて始める</strong>
        </summary>
        <div className="editbox">
          <label>
            件名（何の下書きか）
            <input value={form.caseName} onChange={(e) => setForm({ ...form, caseName: e.target.value })} placeholder="例: 今村さんへの完了報告" />
          </label>
          <label>
            宛先
            <input value={form.recipient} onChange={(e) => setForm({ ...form, recipient: e.target.value })} placeholder="例: 今村さん" />
          </label>
          <label>
            送り方
            <select value={form.channel} onChange={(e) => setForm({ ...form, channel: e.target.value })}>
              {CHANNELS.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </label>
          <label>
            下書き
            <textarea rows={10} value={form.text} onChange={(e) => setForm({ ...form, text: e.target.value })} />
          </label>
          <div className="btn-row">
            <button className="primary" onClick={create} disabled={busy}>
              始める
            </button>
          </div>
        </div>
      </details>

      {done.length ? <div className="eyebrow">最近確定したもの</div> : null}
      {done.map((i) => (
        <Link key={i.id} className="card nav-card" href={`/drafts/${i.id}`}>
          <span className="txt">
            <strong>{i.caseName}</strong>
            <span className="meta">
              {i.recipient}・{i.versions}版で確定
            </span>
          </span>
        </Link>
      ))}
      {err ? <div className="card warn">{err}</div> : null}
    </div>
  );
}
