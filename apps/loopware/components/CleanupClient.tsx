"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { REASON_TAGS_313 } from "@/lib/seed312";
import {
  formatDecisionMd,
  loadStore,
  upsertDecision,
  type DecisionRecord,
} from "@/lib/storage";

type Tab = "cleanup" | "misses";

export default function CleanupClient({
  initialTaskId = "",
  initialTab = "cleanup",
}: {
  initialTaskId?: string;
  initialTab?: Tab;
}) {
  const sp = useSearchParams();
  const taskId = sp.get("task") || initialTaskId;
  const [tab, setTab] = useState<Tab>(
    sp.get("tab") === "misses" ? "misses" : initialTab,
  );
  const [title, setTitle] = useState(taskId ? `Task ${taskId}` : "");
  const [due, setDue] = useState("");
  const [note, setNote] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [results, setResults] = useState<DecisionRecord[]>([]);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    setResults(loadStore().decisions.filter((d) => d.agentId === "313"));
  }, []);

  function toggleTag(t: string) {
    setTags((prev) =>
      prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t],
    );
  }

  async function decide(choice: DecisionRecord["choice"]) {
    const tid = taskId || `manual-${Date.now()}`;
    const rec: DecisionRecord = {
      topicId: tid,
      agentId: "313",
      choice,
      finalText: title || tid,
      reasonTags: tags,
      freeNote: [note, due ? `due=${due}` : ""].filter(Boolean).join(" / ") || undefined,
      decidedAt: new Date().toISOString(),
      decidedVia: "app",
    };
    upsertDecision(rec);
    setResults(loadStore().decisions.filter((d) => d.agentId === "313"));
    setMsg(`記録: ${choice}`);
    try {
      await fetch("/api/decide", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          agentId: "313",
          topicText: title || tid,
          seedId: tid,
          decision: rec,
          todoistTaskId: taskId || null,
        }),
      });
    } catch {
      /* ok */
    }
  }

  return (
    <div>
      <div className="tabs">
        <button
          type="button"
          className={`tab ${tab === "cleanup" ? "active" : ""}`}
          onClick={() => setTab("cleanup")}
        >
          片付ける
        </button>
        <button
          type="button"
          className={`tab ${tab === "misses" ? "active" : ""}`}
          onClick={() => setTab("misses")}
        >
          閉じ漏れ
        </button>
      </div>

      {tab === "cleanup" ? (
        <>
          <p className="meta">Todoist task_id（Slackリンクから渡る）</p>
          <input
            type="text"
            value={taskId}
            readOnly={Boolean(taskId)}
            placeholder="task id"
            onChange={() => undefined}
          />
          <p className="meta" style={{ marginTop: 10 }}>
            タイトル・メモ
          </p>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="タスク名"
          />
          <p className="meta" style={{ marginTop: 10 }}>
            新期日（いつ・優先のとき YYYY-MM-DD。空＝期日を外す案）
          </p>
          <input
            type="text"
            value={due}
            onChange={(e) => setDue(e.target.value)}
            placeholder="2026-11-14 または空"
          />
          <div className="tags" style={{ marginTop: 12 }}>
            {REASON_TAGS_313.map((t) => (
              <button
                key={t}
                type="button"
                className={`tag ${tags.includes(t) ? "on" : ""}`}
                onClick={() => toggleTag(t)}
              >
                {t}
              </button>
            ))}
          </div>
          <input
            type="text"
            style={{ marginTop: 10 }}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="一言・根拠"
          />
          <div className="btn-row" style={{ marginTop: 14 }}>
            <button
              type="button"
              className="primary"
              onClick={() => decide("close")}
            >
              ✅ 済んだ
            </button>
            <button type="button" onClick={() => decide("reschedule")}>
              📅 いつ・優先
            </button>
            <button type="button" onClick={() => decide("drop")}>
              🗑 やめる
            </button>
          </div>
        </>
      ) : (
        <div className="card">
          <h3>閉じ漏れ（段階2）</h3>
          <p className="meta">
            台帳送信済・PRマージ・watch解消・番頭さんの指摘・「これ済んだ」をここに並べる。
            検知スクリプト:{" "}
            <code>scripts/jarvis_todoist_313_done_elsewhere.py</code>
          </p>
          <p className="meta">
            現状は枠のみ。検知結果は API／state から流し込む。
          </p>
        </div>
      )}

      {msg ? <p className="meta">{msg}</p> : null}

      <h2 style={{ fontSize: "1.05rem", marginTop: 28 }}>結果一覧</h2>
      <ul className="list">
        {results.map((r) => (
          <li key={`${r.topicId}-${r.decidedAt}`}>
            <strong>{r.topicId}</strong> · {r.choice} ·{" "}
            {(r.reasonTags || []).join("/") || "-"}
            <div className="btn-row" style={{ marginTop: 6 }}>
              <button
                type="button"
                onClick={() => {
                  void navigator.clipboard.writeText(formatDecisionMd(r));
                  setMsg("コピーした");
                }}
              >
                記録をコピー
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
