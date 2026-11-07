"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  REASON_TAGS_312,
  SEED_TOPICS_312,
  type SeedTopic,
} from "@/lib/seed312";
import {
  formatDecisionMd,
  loadStore,
  upsertDecision,
  type DecisionRecord,
} from "@/lib/storage";

export default function TaskDedupeClient({
  initialTopicId = "",
}: {
  initialTopicId?: string;
}) {
  const sp = useSearchParams();
  const topicFromUrl = sp.get("topic") || initialTopicId;
  const [topicId, setTopicId] = useState(
    topicFromUrl || SEED_TOPICS_312[0].id,
  );
  const [customText, setCustomText] = useState("");
  const [editIndex, setEditIndex] = useState<number | null>(null);
  const [editBody, setEditBody] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [note, setNote] = useState("");
  const [results, setResults] = useState<DecisionRecord[]>([]);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    setResults(loadStore().decisions.filter((d) => d.agentId === "312"));
  }, []);

  useEffect(() => {
    if (topicFromUrl) setTopicId(topicFromUrl);
  }, [topicFromUrl]);

  const topic: SeedTopic | null = useMemo(() => {
    const found = SEED_TOPICS_312.find((t) => t.id === topicId);
    if (found) return found;
    if (topicId === "custom") {
      return {
        id: "custom",
        title: "手入力お題",
        topicText: customText,
        proposals: [
          { index: 1, label: "既存へ追記", body: "（案生成待ち・シード以外）" },
          { index: 2, label: "別タスク作成", body: "（案生成待ち・シード以外）" },
          { index: 3, label: "登録しない", body: "（案生成待ち・シード以外）" },
        ],
      };
    }
    return SEED_TOPICS_312[0];
  }, [topicId, customText]);

  function toggleTag(t: string) {
    setTags((prev) =>
      prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t],
    );
  }

  async function decide(
    choice: DecisionRecord["choice"],
    chosenIndex?: number,
    finalText?: string,
    beforeText?: string,
  ) {
    if (!topic) return;
    const rec: DecisionRecord = {
      topicId: topic.id,
      agentId: "312",
      choice,
      chosenIndex,
      finalText,
      beforeText,
      afterText: finalText,
      reasonTags: tags,
      freeNote: note || undefined,
      decidedAt: new Date().toISOString(),
      decidedVia: "app",
    };
    upsertDecision(rec);
    setResults(loadStore().decisions.filter((d) => d.agentId === "312"));
    setMsg("記録した");
    setEditIndex(null);
    try {
      await fetch("/api/decide", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          agentId: "312",
          topicText: topic.topicText,
          seedId: topic.id,
          proposals: topic.proposals,
          decision: rec,
        }),
      });
    } catch {
      /* local-only ok */
    }
  }

  if (!topic) return null;

  return (
    <div>
      <div className="tabs">
        {SEED_TOPICS_312.map((t) => {
          const done = results.some((r) => r.topicId === t.id);
          return (
            <button
              key={t.id}
              type="button"
              className={`tab ${topicId === t.id ? "active" : ""}`}
              onClick={() => setTopicId(t.id)}
            >
              {t.title}
              {done ? " ✓" : ""}
            </button>
          );
        })}
        <button
          type="button"
          className={`tab ${topicId === "custom" ? "active" : ""}`}
          onClick={() => setTopicId("custom")}
        >
          手入力
        </button>
      </div>

      {topicId === "custom" ? (
        <textarea
          rows={5}
          placeholder="発言と既存タスクをお題として貼る"
          value={customText}
          onChange={(e) => setCustomText(e.target.value)}
        />
      ) : (
        <pre
          style={{
            background: "#fff",
            border: "1px solid var(--line)",
            borderRadius: 10,
            padding: 12,
            whiteSpace: "pre-wrap",
            fontSize: "0.85rem",
          }}
        >
          {topic.topicText}
        </pre>
      )}

      <div className="card-grid three" style={{ marginTop: 16 }}>
        {topic.proposals.map((p) => (
          <div key={p.index} className="card">
            <h3>
              {p.index}. {p.label}
            </h3>
            {editIndex === p.index ? (
              <textarea
                rows={8}
                value={editBody}
                onChange={(e) => setEditBody(e.target.value)}
              />
            ) : (
              <pre>{p.body}</pre>
            )}
            <div className="btn-row">
              {editIndex === p.index ? (
                <button
                  type="button"
                  className="primary"
                  onClick={() =>
                    decide("edit_use", p.index, editBody, p.body)
                  }
                >
                  これで決める
                </button>
              ) : (
                <>
                  <button
                    type="button"
                    className="primary"
                    onClick={() => decide("use", p.index, p.body)}
                  >
                    これを使う
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setEditIndex(p.index);
                      setEditBody(p.body);
                    }}
                  >
                    直して使う
                  </button>
                </>
              )}
            </div>
          </div>
        ))}
      </div>

      <div style={{ marginTop: 16 }}>
        <button
          type="button"
          className="ghost"
          onClick={() => decide("none_of_above")}
        >
          どれも違う
        </button>
      </div>

      <p className="meta" style={{ marginTop: 16 }}>
        決め手（任意）
      </p>
      <div className="tags">
        {REASON_TAGS_312.map((t) => (
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
      <p className="meta" style={{ marginTop: 12 }}>
        一言（どれも違う／補足）
      </p>
      <input
        type="text"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="選択肢外のときなど"
      />

      {msg ? <p className="meta">{msg}</p> : null}

      <h2 style={{ fontSize: "1.05rem", marginTop: 28 }}>結果一覧</h2>
      <ul className="list">
        {results.map((r) => (
          <li key={`${r.topicId}-${r.decidedAt}`}>
            <strong>{r.topicId}</strong> · {r.choice}
            {r.chosenIndex != null ? ` #${r.chosenIndex}` : ""} ·{" "}
            {(r.reasonTags || []).join("/") || "タグなし"}
            <div className="btn-row" style={{ marginTop: 6 }}>
              <button
                type="button"
                onClick={() => {
                  void navigator.clipboard.writeText(formatDecisionMd(r));
                  setMsg("MDをコピーした");
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
