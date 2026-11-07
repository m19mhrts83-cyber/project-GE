"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  REASON_TAGS,
  STORAGE_KEY,
  defaultStore,
  formatResultMd,
  mergeSeedMedia,
  resultForTopic,
  upsertResult,
  type Candidate,
  type Store,
  type Topic,
  type TopicResult,
} from "@/lib/purchaseCompare";

function loadStore(): Store {
  if (typeof window === "undefined") return defaultStore();
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaultStore();
    const parsed = JSON.parse(raw) as Store;
    if (parsed?.version !== 1 || !Array.isArray(parsed.topics)) {
      return defaultStore();
    }
    const seed = defaultStore();
    const hasSeed = parsed.topics.some((t) => t.id === seed.topics[0].id);
    const base: Store = {
      version: 1,
      topics: hasSeed ? parsed.topics : [...seed.topics, ...parsed.topics],
      results: Array.isArray(parsed.results) ? parsed.results : [],
    };
    return mergeSeedMedia(base);
  } catch {
    return defaultStore();
  }
}

function saveStore(store: Store) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
}

function emptyCandidate(n: number): Candidate {
  return {
    id: `c-${Date.now()}-${n}`,
    label: `候補${n}`,
    price: "",
    features: "",
    compatibility: "",
    annualConsumables: "",
    checkedAt: new Date().toISOString().slice(0, 10),
    source: "",
    unknowns: "",
    imageUrl: "",
    imageCredit: "",
  };
}

function CandidatePhoto({
  label,
  imageUrl,
  imageCredit,
}: {
  label: string;
  imageUrl?: string;
  imageCredit?: string;
}) {
  const src = imageUrl?.trim();
  return (
    <div
      style={{
        width: "100%",
        aspectRatio: "1 / 1",
        borderRadius: 12,
        background: "#f0ebe3",
        border: "1px solid var(--line)",
        overflow: "hidden",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        position: "relative",
      }}
    >
      {src ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={src}
          alt={label}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "contain",
            background: "#fff",
          }}
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={(e) => {
            const el = e.currentTarget;
            el.style.display = "none";
            const fallback = el.nextElementSibling as HTMLElement | null;
            if (fallback) fallback.style.display = "flex";
          }}
        />
      ) : null}
      <div
        style={{
          display: src ? "none" : "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 4,
          padding: 12,
          color: "var(--muted)",
          fontSize: 13,
          textAlign: "center",
          position: src ? "absolute" : "static",
          inset: 0,
        }}
      >
        <span>写真なし</span>
        <span className="meta">編集からURLまたは端末写真を追加</span>
      </div>
      {imageCredit && src ? (
        <span
          className="meta"
          style={{
            position: "absolute",
            left: 8,
            bottom: 6,
            right: 8,
            fontSize: 11,
            background: "#ffffffcc",
            borderRadius: 6,
            padding: "2px 6px",
          }}
        >
          {imageCredit}
        </span>
      ) : null}
    </div>
  );
}

export default function PurchaseCompareClient() {
  const [store, setStore] = useState<Store | null>(null);
  const [topicId, setTopicId] = useState<string>("");
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [conditions, setConditions] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [skipAll, setSkipAll] = useState(false);
  const [selectReasons, setSelectReasons] = useState<string[]>([]);
  const [skipReasons, setSkipReasons] = useState<Record<string, string[]>>({});
  const [editingId, setEditingId] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [postNote, setPostNote] = useState("");
  const [postStatus, setPostStatus] = useState<
    "purchased" | "cancelled" | "still_considering"
  >("purchased");
  const [postSat, setPostSat] = useState<
    "satisfied" | "regret" | "mixed" | "unknown"
  >("unknown");
  const [newTitle, setNewTitle] = useState("");
  const [newConditions, setNewConditions] = useState("");

  useEffect(() => {
    const s = loadStore();
    setStore(s);
    saveStore(s);
    const first = s.topics[0];
    if (first) {
      setTopicId(first.id);
      setCandidates(structuredClone(first.candidates));
      setConditions(first.conditions);
      const existing = resultForTopic(s, first.id);
      if (existing) {
        setSelectedId(existing.selectedCandidateId);
        setSkipAll(existing.decision === "skip_all");
        setSelectReasons(existing.selectReasons || []);
        setSkipReasons(existing.skipReasons || {});
        if (existing.postPurchase) {
          setPostNote(existing.postPurchase.note || "");
          setPostStatus(existing.postPurchase.status);
          setPostSat(existing.postPurchase.satisfaction);
        }
      }
    }
  }, []);

  const topic = useMemo(
    () => store?.topics.find((t) => t.id === topicId) || null,
    [store, topicId],
  );

  const existingResult = useMemo(
    () => (store && topicId ? resultForTopic(store, topicId) : undefined),
    [store, topicId],
  );

  const switchTopic = useCallback(
    (id: string) => {
      if (!store) return;
      const t = store.topics.find((x) => x.id === id);
      if (!t) return;
      setTopicId(id);
      setCandidates(structuredClone(t.candidates));
      setConditions(t.conditions);
      setEditingId(null);
      setCopied(false);
      const existing = resultForTopic(store, id);
      setSelectedId(existing?.selectedCandidateId ?? null);
      setSkipAll(existing?.decision === "skip_all");
      setSelectReasons(existing?.selectReasons || []);
      setSkipReasons(existing?.skipReasons || {});
      setPostNote(existing?.postPurchase?.note || "");
      setPostStatus(existing?.postPurchase?.status || "purchased");
      setPostSat(existing?.postPurchase?.satisfaction || "unknown");
    },
    [store],
  );

  const persist = useCallback((next: Store) => {
    setStore(next);
    saveStore(next);
  }, []);

  const updateCandidate = (id: string, patch: Partial<Candidate>) => {
    setCandidates((prev) =>
      prev.map((c) => (c.id === id ? { ...c, ...patch } : c)),
    );
  };

  const toggleTag = (
    list: string[],
    tag: string,
    setter: (v: string[]) => void,
  ) => {
    setter(
      list.includes(tag) ? list.filter((t) => t !== tag) : [...list, tag],
    );
  };

  const toggleSkipTag = (candId: string, tag: string) => {
    setSkipReasons((prev) => {
      const cur = prev[candId] || [];
      const next = cur.includes(tag)
        ? cur.filter((t) => t !== tag)
        : [...cur, tag];
      return { ...prev, [candId]: next };
    });
  };

  const saveDecision = () => {
    if (!store || !topic) return;
    if (!skipAll && !selectedId) {
      window.alert("候補を1つ選ぶか、「すべて見送り」を選んでください。");
      return;
    }
    const result: TopicResult = {
      topicId: topic.id,
      decision: skipAll ? "skip_all" : "selected",
      selectedCandidateId: skipAll ? null : selectedId,
      selectReasons: skipAll ? [] : selectReasons,
      skipReasons,
      candidatesSnapshot: structuredClone(candidates),
      conditionsSnapshot: conditions,
      decidedAt: new Date().toISOString(),
      postPurchase: existingResult?.postPurchase,
    };
    const topics = store.topics.map((t) =>
      t.id === topic.id
        ? { ...t, conditions, candidates: structuredClone(candidates) }
        : t,
    );
    persist(upsertResult({ ...store, topics }, result));
  };

  const savePostPurchase = () => {
    if (!store || !topic) return;
    const base =
      existingResult ||
      ({
        topicId: topic.id,
        decision: skipAll ? "skip_all" : "selected",
        selectedCandidateId: selectedId,
        selectReasons,
        skipReasons,
        candidatesSnapshot: structuredClone(candidates),
        conditionsSnapshot: conditions,
        decidedAt: new Date().toISOString(),
      } as TopicResult);
    const result: TopicResult = {
      ...base,
      postPurchase: {
        at: new Date().toISOString().slice(0, 10),
        status: postStatus,
        satisfaction: postSat,
        note: postNote.trim(),
      },
    };
    persist(upsertResult(store, result));
  };

  const copyMd = async () => {
    if (!topic) return;
    const md = formatResultMd(topic, existingResult, candidates);
    await navigator.clipboard.writeText(md);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  };

  const addTopic = () => {
    if (!store) return;
    const title = newTitle.trim();
    const cond = newConditions.trim();
    if (!title || !cond) {
      window.alert("タイトルと条件を入力してください。");
      return;
    }
    const id = `topic-${Date.now()}`;
    const t: Topic = {
      id,
      title,
      conditions: cond,
      candidates: [emptyCandidate(1), emptyCandidate(2), emptyCandidate(3)],
    };
    const next = { ...store, topics: [...store.topics, t] };
    persist(next);
    setNewTitle("");
    setNewConditions("");
    setTopicId(id);
    setCandidates(structuredClone(t.candidates));
    setConditions(t.conditions);
    setSelectedId(null);
    setSkipAll(false);
    setSelectReasons([]);
    setSkipReasons({});
  };

  if (!store || !topic) {
    return <p className="sub">読み込み中…</p>;
  }

  return (
    <div style={{ display: "grid", gap: 20 }}>
      <section className="card">
        <header>
          <strong>お題</strong>
        </header>
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 8,
            marginTop: 10,
          }}
        >
          {store.topics.map((t) => (
            <button
              key={t.id}
              type="button"
              className="btn"
              style={{
                opacity: t.id === topicId ? 1 : 0.65,
                outline: t.id === topicId ? "2px solid var(--accent)" : undefined,
              }}
              onClick={() => switchTopic(t.id)}
            >
              {t.title}
              {resultForTopic(store, t.id) ? " ✓" : ""}
            </button>
          ))}
        </div>
        <label className="sub" style={{ display: "block", marginTop: 14 }}>
          買い物の条件
          <textarea
            value={conditions}
            onChange={(e) => setConditions(e.target.value)}
            rows={5}
            style={{
              width: "100%",
              marginTop: 6,
              font: "inherit",
              padding: 10,
              borderRadius: 8,
              border: "1px solid var(--line)",
            }}
          />
        </label>
      </section>

      <section>
        <h2 style={{ fontSize: 18, margin: "0 0 12px" }}>候補を比べる</h2>
        <div
          style={{
            display: "grid",
            gap: 12,
            gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
          }}
        >
          {candidates.map((c) => {
            const selected = !skipAll && selectedId === c.id;
            return (
              <article
                key={c.id}
                className="card"
                style={{
                  border: selected
                    ? "2px solid var(--accent)"
                    : "1px solid var(--line)",
                  display: "flex",
                  flexDirection: "column",
                  gap: 8,
                }}
              >
                <CandidatePhoto
                  label={c.label}
                  imageUrl={c.imageUrl}
                  imageCredit={c.imageCredit}
                />
                <header
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    gap: 8,
                    alignItems: "flex-start",
                  }}
                >
                  <strong style={{ fontSize: 15 }}>{c.label}</strong>
                  <button
                    type="button"
                    className="btn"
                    onClick={() => {
                      setSkipAll(false);
                      setSelectedId(c.id);
                    }}
                  >
                    {selected ? "選択中" : "これを選ぶ"}
                  </button>
                </header>
                {editingId === c.id ? (
                  <div style={{ display: "grid", gap: 6 }}>
                    {(
                      [
                        ["label", "名前"],
                        ["price", "価格"],
                        ["features", "機能"],
                        ["compatibility", "互換性"],
                        ["annualConsumables", "年間消耗品代"],
                        ["checkedAt", "確認日"],
                        ["source", "情報源"],
                        ["unknowns", "不明点"],
                        ["imageUrl", "写真URL"],
                        ["imageCredit", "写真クレジット"],
                      ] as const
                    ).map(([key, label]) => (
                      <label key={key} className="meta">
                        {label}
                        <input
                          value={c[key] || ""}
                          onChange={(e) =>
                            updateCandidate(c.id, { [key]: e.target.value })
                          }
                          style={{
                            width: "100%",
                            marginTop: 2,
                            font: "inherit",
                            padding: 6,
                            borderRadius: 6,
                            border: "1px solid var(--line)",
                          }}
                        />
                      </label>
                    ))}
                    <label className="meta">
                      端末から写真を追加
                      <input
                        type="file"
                        accept="image/*"
                        style={{ display: "block", marginTop: 4 }}
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          if (!file) return;
                          if (file.size > 2_500_000) {
                            window.alert(
                              "2.5MB以下の画像にしてください（localStorage制限）。",
                            );
                            e.target.value = "";
                            return;
                          }
                          const reader = new FileReader();
                          reader.onload = () => {
                            const dataUrl = String(reader.result || "");
                            updateCandidate(c.id, {
                              imageUrl: dataUrl,
                              imageCredit: c.imageCredit || "端末アップロード",
                            });
                          };
                          reader.readAsDataURL(file);
                          e.target.value = "";
                        }}
                      />
                    </label>
                    {c.imageUrl ? (
                      <button
                        type="button"
                        className="btn"
                        onClick={() =>
                          updateCandidate(c.id, {
                            imageUrl: "",
                            imageCredit: "",
                          })
                        }
                      >
                        写真を消す
                      </button>
                    ) : null}
                    <button
                      type="button"
                      className="btn"
                      onClick={() => setEditingId(null)}
                    >
                      編集を閉じる
                    </button>
                  </div>
                ) : (
                  <dl
                    className="meta"
                    style={{ margin: 0, display: "grid", gap: 4 }}
                  >
                    <div>
                      <dt style={{ display: "inline" }}>価格：</dt>
                      <dd style={{ display: "inline", margin: 0 }}>{c.price}</dd>
                    </div>
                    <div>
                      <dt style={{ display: "inline" }}>機能：</dt>
                      <dd style={{ display: "inline", margin: 0 }}>
                        {c.features}
                      </dd>
                    </div>
                    <div>
                      <dt style={{ display: "inline" }}>互換性：</dt>
                      <dd style={{ display: "inline", margin: 0 }}>
                        {c.compatibility}
                      </dd>
                    </div>
                    <div>
                      <dt style={{ display: "inline" }}>年間消耗品：</dt>
                      <dd style={{ display: "inline", margin: 0 }}>
                        {c.annualConsumables}
                      </dd>
                    </div>
                    <div>
                      <dt style={{ display: "inline" }}>確認日：</dt>
                      <dd style={{ display: "inline", margin: 0 }}>
                        {c.checkedAt}
                      </dd>
                    </div>
                    <div>
                      <dt style={{ display: "inline" }}>情報源：</dt>
                      <dd style={{ display: "inline", margin: 0 }}>
                        {c.source}
                      </dd>
                    </div>
                    <div>
                      <dt style={{ display: "inline" }}>不明点：</dt>
                      <dd style={{ display: "inline", margin: 0 }}>
                        {c.unknowns}
                      </dd>
                    </div>
                  </dl>
                )}
                {(c.referenceLinks?.length || c.amazonUrl) &&
                editingId !== c.id ? (
                  <div
                    className="meta"
                    style={{
                      display: "grid",
                      gap: 4,
                      marginTop: 2,
                      paddingTop: 6,
                      borderTop: "1px solid var(--line)",
                    }}
                  >
                    {c.referenceLinks?.map((r) => (
                      <a
                        key={r.url}
                        href={r.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ color: "var(--accent)", wordBreak: "break-all" }}
                      >
                        根拠: {r.label} ↗
                      </a>
                    ))}
                    {c.amazonUrl ? (
                      <a
                        href={c.amazonUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ color: "var(--accent)", wordBreak: "break-all" }}
                      >
                        Amazonで見る ↗
                      </a>
                    ) : null}
                  </div>
                ) : null}
                <button
                  type="button"
                  className="btn"
                  style={{ alignSelf: "flex-start" }}
                  onClick={() =>
                    setEditingId(editingId === c.id ? null : c.id)
                  }
                >
                  情報を直す
                </button>
                <div>
                  <p className="meta" style={{ margin: "4px 0" }}>
                    この候補の見送り理由（任意）
                  </p>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {REASON_TAGS.map((tag) => {
                      const on = (skipReasons[c.id] || []).includes(tag);
                      return (
                        <button
                          key={tag}
                          type="button"
                          className="btn"
                          style={{
                            fontSize: 12,
                            padding: "4px 8px",
                            opacity: on ? 1 : 0.55,
                            background: on ? "var(--accent)" : undefined,
                            color: on ? "#fff" : undefined,
                          }}
                          onClick={() => toggleSkipTag(c.id, tag)}
                        >
                          {tag}
                        </button>
                      );
                    })}
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      </section>

      <section className="card">
        <header>
          <strong>判断</strong>
        </header>
        <p className="sub" style={{ marginTop: 8 }}>
          1つ選ぶか、すべて見送ります。理由タグは任意です。
        </p>
        <label
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            marginTop: 10,
          }}
        >
          <input
            type="checkbox"
            checked={skipAll}
            onChange={(e) => {
              setSkipAll(e.target.checked);
              if (e.target.checked) setSelectedId(null);
            }}
          />
          すべて見送り（どれも違う）
        </label>
        {!skipAll ? (
          <div style={{ marginTop: 12 }}>
            <p className="meta">選択理由（任意）</p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {REASON_TAGS.map((tag) => {
                const on = selectReasons.includes(tag);
                return (
                  <button
                    key={tag}
                    type="button"
                    className="btn"
                    style={{
                      fontSize: 12,
                      padding: "4px 8px",
                      opacity: on ? 1 : 0.55,
                      background: on ? "var(--accent)" : undefined,
                      color: on ? "#fff" : undefined,
                    }}
                    onClick={() =>
                      toggleTag(selectReasons, tag, setSelectReasons)
                    }
                  >
                    {tag}
                  </button>
                );
              })}
            </div>
          </div>
        ) : null}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginTop: 16 }}>
          <button type="button" className="btn" onClick={saveDecision}>
            この判断を保存
          </button>
          <button type="button" className="btn" onClick={copyMd}>
            {copied ? "コピーしました" : "結果をMDでコピー"}
          </button>
        </div>
        {existingResult ? (
          <p className="meta" style={{ marginTop: 10 }}>
            保存済み：{existingResult.decision === "skip_all"
              ? "すべて見送り"
              : `選択 ${
                  candidates.find(
                    (c) => c.id === existingResult.selectedCandidateId,
                  )?.label || existingResult.selectedCandidateId
                }`}{" "}
            （{existingResult.decidedAt.slice(0, 19).replace("T", " ")}）
          </p>
        ) : null}
      </section>

      <section className="card">
        <header>
          <strong>購入後の追記</strong>
        </header>
        <p className="sub" style={{ marginTop: 8 }}>
          買ったあと・見送ったあとの感想を残すと、次の提案精度が上がります。
        </p>
        <div
          style={{
            display: "grid",
            gap: 10,
            marginTop: 10,
            maxWidth: 480,
          }}
        >
          <label className="meta">
            状態
            <select
              value={postStatus}
              onChange={(e) =>
                setPostStatus(
                  e.target.value as
                    | "purchased"
                    | "cancelled"
                    | "still_considering",
                )
              }
              style={{ display: "block", marginTop: 4, font: "inherit" }}
            >
              <option value="purchased">購入済み</option>
              <option value="still_considering">検討中</option>
              <option value="cancelled">中止</option>
            </select>
          </label>
          <label className="meta">
            評価
            <select
              value={postSat}
              onChange={(e) =>
                setPostSat(
                  e.target.value as
                    | "satisfied"
                    | "regret"
                    | "mixed"
                    | "unknown",
                )
              }
              style={{ display: "block", marginTop: 4, font: "inherit" }}
            >
              <option value="unknown">未記入</option>
              <option value="satisfied">満足</option>
              <option value="mixed">どちらとも</option>
              <option value="regret">後悔</option>
            </select>
          </label>
          <label className="meta">
            一言
            <textarea
              value={postNote}
              onChange={(e) => setPostNote(e.target.value)}
              rows={3}
              style={{
                width: "100%",
                marginTop: 4,
                font: "inherit",
                padding: 8,
                borderRadius: 8,
                border: "1px solid var(--line)",
              }}
            />
          </label>
          <button type="button" className="btn" onClick={savePostPurchase}>
            追記を保存
          </button>
        </div>
      </section>

      <section className="card">
        <header>
          <strong>新しいお題</strong>
        </header>
        <p className="sub" style={{ marginTop: 8 }}>
          次の買い物用。候補は空の3枠から手で埋めます（AI自動提案は後続）。
        </p>
        <div style={{ display: "grid", gap: 8, marginTop: 10, maxWidth: 560 }}>
          <input
            placeholder="タイトル（例：掃除機）"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            style={{
              font: "inherit",
              padding: 8,
              borderRadius: 8,
              border: "1px solid var(--line)",
            }}
          />
          <textarea
            placeholder="予算・必須条件・今使っている物など"
            value={newConditions}
            onChange={(e) => setNewConditions(e.target.value)}
            rows={3}
            style={{
              font: "inherit",
              padding: 8,
              borderRadius: 8,
              border: "1px solid var(--line)",
            }}
          />
          <button type="button" className="btn" onClick={addTopic}>
            お題を追加
          </button>
        </div>
      </section>
    </div>
  );
}
