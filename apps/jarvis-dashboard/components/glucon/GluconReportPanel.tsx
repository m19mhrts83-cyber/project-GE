"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, useTransition } from "react";
import {
  analyzeGluconResultBody,
  consultGluconDraft,
  generateGluconClarify,
  generateGluconDrafts,
  generateGluconFacts,
  generateGluconFinal,
  queueGluconPost,
  saveGluconClarifyAnswers,
  saveGluconDraft,
  skipGluconDraft,
} from "@/app/actions/glucon";
import {
  canQueueGluconDraft,
  isNoResultBody,
} from "@/lib/glucon/postGuard";
import type {
  GluconActiveCycle,
  GluconClarifyItem,
  GluconConsultTurn,
  GluconDraftPayload,
  GluconDraftRow,
  GluconFactItem,
  GluconJournalDay,
  GluconLastResultCoverage,
  GluconMemberHeaderStatus,
  GluconMonthlyDigestPreview,
  GluconReportKind,
  GluconResultPhase,
  ResultScoringHints,
} from "@/lib/glucon/types";
import { WESTUDY_FORUM_URLS } from "@/lib/glucon/types";

const KIND_LABEL: Record<GluconReportKind, string> = {
  activity: "活動報告",
  result: "成果報告",
};

function nextYmdClient(ymd: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(ymd);
  if (!m) return ymd;
  const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]) + 1));
  return d.toISOString().slice(0, 10);
}

function todayYmdClient(): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const y = parts.find((p) => p.type === "year")?.value;
  const mo = parts.find((p) => p.type === "month")?.value;
  const d = parts.find((p) => p.type === "day")?.value;
  return `${y}-${mo}-${d}`;
}

function draftFor(
  drafts: GluconDraftRow[],
  kind: GluconReportKind,
): GluconDraftRow | null {
  return drafts.find((d) => d.kind === kind) || null;
}

function ResultScoringChecklist({ body }: { body: string }) {
  const [hints, setHints] = useState<ResultScoringHints | null>(null);
  const [open, setOpen] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const t = setTimeout(() => {
      void (async () => {
        const r = await analyzeGluconResultBody(body);
        if (cancelled) return;
        if (r.ok && r.hints) setHints(r.hints);
        else setHints(null);
      })();
    }, 350);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [body]);

  if (isNoResultBody(body)) return null;

  return (
    <details
      open={open}
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
      style={{ marginTop: "0.75rem" }}
    >
      <summary style={{ cursor: "pointer" }}>観点チェック（著者向け）</summary>
      <p className="meta" style={{ marginTop: "0.5rem" }}>
        {hints?.disclaimer ||
          "運営採点の保証ではない。投稿前の自己チェックです。"}
      </p>
      {hints?.suggestions?.length ? (
        <ul style={{ fontSize: "0.85rem", marginTop: "0.35rem" }}>
          {hints.suggestions.map((s) => (
            <li key={s.ruleId}>
              候補: {s.mid} Lv{s.level}「{s.viewpoint}」（目安 {s.points} 点）
              {s.matchedKeywords.length
                ? ` — キーワード: ${s.matchedKeywords.join("、")}`
                : ""}
            </li>
          ))}
        </ul>
      ) : (
        <p className="meta">キーワード一致の候補ルールはまだありません。</p>
      )}
      {hints?.gaps?.length ? (
        <>
          <p className="meta" style={{ marginTop: "0.5rem" }}>
            不足しがちな観点
          </p>
          <ul style={{ fontSize: "0.85rem" }}>
            {hints.gaps.map((g) => (
              <li key={g}>{g}</li>
            ))}
          </ul>
        </>
      ) : hints ? (
        <p className="meta">数字・手順・題名の簡易チェックは問題なさそうです。</p>
      ) : null}
    </details>
  );
}

function ConsultPanel({
  kind,
  body,
  consult,
  onApplyRevised,
  pending,
  start,
}: {
  kind: GluconReportKind;
  body: string;
  consult: GluconConsultTurn[];
  onApplyRevised: (text: string) => void;
  pending: boolean;
  start: (fn: () => Promise<void>) => void;
}) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [reply, setReply] = useState<string | null>(null);
  const [pendingRevise, setPendingRevise] = useState<string | null>(null);

  return (
    <div style={{ marginTop: "0.75rem" }}>
      <strong style={{ fontSize: "0.9rem" }}>聞く／直す</strong>
      <p className="meta">本文を見ながら相談・部分修正できます。</p>
      <textarea
        value={q}
        onChange={(e) => setQ(e.target.value)}
        rows={3}
        placeholder="例: 工夫の部分を膨らませて／数字をもっと前に"
        style={{
          width: "100%",
          fontSize: "0.85rem",
          marginTop: "0.35rem",
        }}
        disabled={pending}
      />
      <div className="qe-form-actions" style={{ gap: "0.5rem", flexWrap: "wrap" }}>
        <button
          type="button"
          className="btn"
          disabled={pending || !q.trim()}
          onClick={() => {
            setErr(null);
            setReply(null);
            setPendingRevise(null);
            start(async () => {
              const r = await consultGluconDraft({
                kind,
                mode: "ask",
                prompt: q,
                body,
              });
              if (!r.ok) {
                setErr(r.error || "失敗");
                return;
              }
              setReply(r.reply || "");
              router.refresh();
            });
          }}
        >
          聞く
        </button>
        <button
          type="button"
          className="btn"
          disabled={pending || !q.trim()}
          onClick={() => {
            setErr(null);
            setReply(null);
            setPendingRevise(null);
            start(async () => {
              const r = await consultGluconDraft({
                kind,
                mode: "revise",
                prompt: q,
                body,
              });
              if (!r.ok) {
                setErr(r.error || "失敗");
                return;
              }
              setReply(r.reply || "");
              if (r.revisedBody) setPendingRevise(r.revisedBody);
              router.refresh();
            });
          }}
        >
          この指示で直す
        </button>
      </div>
      {err ? <p className="qe-err">{err}</p> : null}
      {reply ? (
        <pre
          style={{
            whiteSpace: "pre-wrap",
            fontSize: "0.8rem",
            marginTop: "0.5rem",
            maxHeight: 140,
            overflow: "auto",
          }}
        >
          {reply}
        </pre>
      ) : null}
      {pendingRevise ? (
        <div className="card" style={{ marginTop: "0.5rem" }}>
          <strong>修正案</strong>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: "0.5rem",
              marginTop: "0.35rem",
            }}
          >
            <div>
              <p className="meta">修正前</p>
              <pre
                style={{
                  whiteSpace: "pre-wrap",
                  fontSize: "0.72rem",
                  maxHeight: 180,
                  overflow: "auto",
                }}
              >
                {body}
              </pre>
            </div>
            <div>
              <p className="meta">修正後</p>
              <pre
                style={{
                  whiteSpace: "pre-wrap",
                  fontSize: "0.72rem",
                  maxHeight: 180,
                  overflow: "auto",
                }}
              >
                {pendingRevise}
              </pre>
            </div>
          </div>
          <div className="qe-form-actions" style={{ gap: "0.5rem" }}>
            <button
              type="button"
              className="btn"
              onClick={() => {
                onApplyRevised(pendingRevise);
                setPendingRevise(null);
              }}
            >
              反映
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => setPendingRevise(null)}
            >
              破棄
            </button>
          </div>
        </div>
      ) : null}
      {consult.length ? (
        <details style={{ marginTop: "0.5rem" }}>
          <summary style={{ cursor: "pointer" }}>
            相談履歴（{consult.length}）
          </summary>
          <ul style={{ fontSize: "0.78rem" }}>
            {consult
              .slice()
              .reverse()
              .map((t, i) => (
                <li key={`${t.at}-${i}`}>
                  [{t.mode}] {t.prompt.slice(0, 60)}
                  {t.prompt.length > 60 ? "…" : ""}
                </li>
              ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}

function DraftActions({
  cycle,
  kind,
  body,
  status,
  setStatus,
  pending,
  start,
  postError,
  coveredFrom,
  coveredTo,
}: {
  cycle: GluconActiveCycle;
  kind: GluconReportKind;
  body: string;
  status: string;
  setStatus: (s: GluconDraftRow["status"]) => void;
  pending: boolean;
  start: (fn: () => Promise<void>) => void;
  postError?: string | null;
  coveredFrom?: string;
  coveredTo?: string;
}) {
  const router = useRouter();
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const forumUrl = WESTUDY_FORUM_URLS[kind];
  const queueStatusForUi =
    status === "skipped" && !(kind === "result" && isNoResultBody(body))
      ? "ready"
      : status;
  const canQueue = canQueueGluconDraft({
    kind,
    body,
    status: queueStatusForUi,
  });

  return (
    <>
      <div className="qe-form-actions" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
        <button
          type="button"
          className="btn"
          disabled={pending}
          onClick={() => {
            setErr(null);
            setMsg(null);
            start(async () => {
              const r = await saveGluconDraft(cycle.periodKey, kind, body);
              if (!r.ok) {
                setErr(r.error || "保存失敗");
                return;
              }
              if (r.draft) setStatus(r.draft.status);
              setMsg(
                r.draft?.status === "skipped"
                  ? "保存しました（成果なしのためスキップ状態を維持）"
                  : "保存しました",
              );
              router.refresh();
            });
          }}
        >
          保存
        </button>
        <button
          type="button"
          className="btn"
          disabled={pending}
          onClick={() => {
            setErr(null);
            setMsg(null);
            start(async () => {
              const r = await skipGluconDraft(cycle.periodKey, kind);
              if (!r.ok) {
                setErr(r.error || "スキップ失敗");
                return;
              }
              setStatus("skipped");
              setMsg("スキップしました");
              router.refresh();
            });
          }}
        >
          投稿スキップ
        </button>
        <button
          type="button"
          className="btn"
          disabled={pending || !canQueue}
          onClick={() => setConfirmOpen(true)}
          title={
            !canQueue
              ? "成果なし・空本文・投稿済み／待ちは投稿できません"
              : undefined
          }
        >
          WeStudy に投稿
        </button>
        <button
          type="button"
          className="btn"
          disabled={!body.trim()}
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(body);
              setMsg("本文をコピーしました（フォールバック）");
            } catch {
              setErr("コピーに失敗しました");
            }
          }}
        >
          コピー
        </button>
        <a className="btn" href={forumUrl} target="_blank" rel="noreferrer">
          板を開く
        </a>
      </div>

      {kind === "result" && isNoResultBody(body) ? (
        <p className="meta">
          成果なしの本文のため「WeStudy に投稿」は使えません。投稿スキップのままで問題ありません。
        </p>
      ) : null}
      {postError ? <p className="qe-err">投稿エラー: {postError}</p> : null}
      {err ? <p className="qe-err">{err}</p> : null}
      {msg ? <p className="meta">{msg}</p> : null}

      {confirmOpen ? (
        <div
          role="dialog"
          aria-modal="true"
          className="card"
          style={{
            marginTop: "0.75rem",
            border: "1px solid var(--border, #888)",
            background: "var(--panel, #111)",
          }}
        >
          <strong>投稿確認</strong>
          <p className="meta">
            板: {KIND_LABEL[kind]}（{forumUrl}）
            <br />
            提出期限: {cycle.reportDeadline} ／ グルコン: {cycle.gluconDate}
          </p>
          <pre
            style={{
              whiteSpace: "pre-wrap",
              maxHeight: 220,
              overflow: "auto",
              fontSize: "0.8rem",
            }}
          >
            {body}
          </pre>
          <div className="qe-form-actions" style={{ gap: "0.5rem" }}>
            <button
              type="button"
              className="btn"
              disabled={pending}
              onClick={() => {
                setConfirmOpen(false);
                setErr(null);
                setMsg(null);
                start(async () => {
                  const saved = await saveGluconDraft(
                    cycle.periodKey,
                    kind,
                    body,
                  );
                  if (!saved.ok) {
                    setErr(saved.error || "保存失敗");
                    return;
                  }
                  if (saved.draft) setStatus(saved.draft.status);
                  if (
                    saved.draft?.status === "skipped" ||
                    (kind === "result" && isNoResultBody(body))
                  ) {
                    setErr(
                      "成果なしのため投稿キューに入れませんでした（スキップ状態を維持）。",
                    );
                    router.refresh();
                    return;
                  }
                  const r = await queueGluconPost(cycle.periodKey, kind, {
                    coveredFrom,
                    coveredTo,
                  });
                  if (!r.ok) {
                    setErr(r.error || "キュー投入失敗");
                    return;
                  }
                  setStatus("queued");
                  setMsg(
                    "投稿待ちに入れました。Mac で jarvis_westudy_forum_post_worker.py を実行してください。",
                  );
                  router.refresh();
                });
              }}
            >
              これで投稿してよい
            </button>
            <button
              type="button"
              className="btn"
              disabled={pending}
              onClick={() => setConfirmOpen(false)}
            >
              キャンセル
            </button>
          </div>
        </div>
      ) : null}
    </>
  );
}

function ActivityEditor({
  cycle,
  initial,
}: {
  cycle: GluconActiveCycle;
  initial: GluconDraftRow | null;
}) {
  const [pending, start] = useTransition();
  const [body, setBody] = useState(initial?.body || "");
  const [status, setStatus] = useState(initial?.status || "draft");
  const payload = (initial?.payload || {}) as GluconDraftPayload;

  useEffect(() => {
    setBody(initial?.body || "");
    setStatus(initial?.status || "draft");
  }, [initial?.id, initial?.body, initial?.status, initial?.updated_at]);

  return (
    <section className="card">
      <header>
        <span className="lvl">{KIND_LABEL.activity}</span>
        <strong>
          {initial?.title || `${cycle.periodKey} ${KIND_LABEL.activity}`}
        </strong>
        <span className="meta" style={{ marginLeft: "0.5rem" }}>
          status: {status}
        </span>
      </header>
      <p className="meta">
        成果候補は成果報告側へ優先。活動は仕込み・学習・進行中が中心です。
      </p>
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        rows={14}
        style={{
          width: "100%",
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
          fontSize: "0.85rem",
          lineHeight: 1.45,
          marginTop: "0.5rem",
        }}
        disabled={pending}
        placeholder="活動報告の本文"
      />
      <ConsultPanel
        kind="activity"
        body={body}
        consult={payload.consult || []}
        onApplyRevised={setBody}
        pending={pending}
        start={start}
      />
      <DraftActions
        cycle={cycle}
        kind="activity"
        body={body}
        status={status}
        setStatus={setStatus}
        pending={pending}
        start={start}
        postError={initial?.post_error}
      />
    </section>
  );
}

function ResultEditor({
  cycle,
  initial,
  lastResultCoverage,
  today,
}: {
  cycle: GluconActiveCycle;
  initial: GluconDraftRow | null;
  lastResultCoverage?: GluconLastResultCoverage | null;
  today: string;
}) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [body, setBody] = useState(initial?.body || "");
  const [status, setStatus] = useState(initial?.status || "draft");
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const payload = (initial?.payload || {}) as GluconDraftPayload;
  const phase: GluconResultPhase = payload.phase || "facts";
  const [facts, setFacts] = useState<GluconFactItem[]>(payload.facts || []);
  const [clarify, setClarify] = useState<GluconClarifyItem[]>(
    payload.clarify || [],
  );
  const defaultFrom = lastResultCoverage?.covered_to
    ? nextYmdClient(lastResultCoverage.covered_to)
    : cycle.journalFrom;
  const defaultTo = today || todayYmdClient();
  const [coveredFrom, setCoveredFrom] = useState(
    payload.covered_from || defaultFrom,
  );
  const [coveredTo, setCoveredTo] = useState(payload.covered_to || defaultTo);

  useEffect(() => {
    setBody(initial?.body || "");
    setStatus(initial?.status || "draft");
    const pl = (initial?.payload || {}) as GluconDraftPayload;
    setFacts(pl.facts || []);
    setClarify(pl.clarify || []);
    if (pl.covered_from) setCoveredFrom(pl.covered_from);
    if (pl.covered_to) setCoveredTo(pl.covered_to);
  }, [initial?.id, initial?.body, initial?.status, initial?.updated_at]);

  const stepLabel = useMemo(() => {
    if (phase === "facts") return "① 事実確認";
    if (phase === "clarify") return "② 確認質問";
    return "③ 最終稿";
  }, [phase]);

  return (
    <section className="card">
      <header>
        <span className="lvl">{KIND_LABEL.result}</span>
        <strong>
          {initial?.title || `${cycle.periodKey} ${KIND_LABEL.result}`}
        </strong>
        <span className="meta" style={{ marginLeft: "0.5rem" }}>
          status: {status} ／ {stepLabel}
        </span>
      </header>
      <p className="meta">
        神・大家さんポイントが貯まるのは成果報告です。空室の早期入居付けなども成果候補として扱います。
        月次に限らず、前回報告以降〜今回の期間でまとめられます（Journal sync
        は直近約90日が実用範囲）。
      </p>

      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "0.75rem",
          alignItems: "flex-end",
          marginTop: "0.5rem",
        }}
      >
        <label style={{ fontSize: "0.85rem" }}>
          対象期間（開始）
          <input
            type="date"
            value={coveredFrom}
            onChange={(e) => setCoveredFrom(e.target.value)}
            disabled={pending}
            style={{ display: "block", marginTop: 4 }}
          />
        </label>
        <label style={{ fontSize: "0.85rem" }}>
          対象期間（終了）
          <input
            type="date"
            value={coveredTo}
            onChange={(e) => setCoveredTo(e.target.value)}
            disabled={pending}
            style={{ display: "block", marginTop: 4 }}
          />
        </label>
      </div>
      <p className="meta" style={{ marginTop: "0.35rem" }}>
        {lastResultCoverage?.covered_to
          ? `前回報告: ${lastResultCoverage.covered_to} まで${
              lastResultCoverage.posted_at
                ? `（投稿 ${String(lastResultCoverage.posted_at).slice(0, 10)}）`
                : ""
            }`
          : "前回報告の履歴なし（初回まとめ可。長い期間はスレッド下書き推奨）"}
      </p>

      <div className="qe-form-actions" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
        <button
          type="button"
          className="btn"
          disabled={pending}
          onClick={() => {
            setErr(null);
            setMsg(null);
            start(async () => {
              const r = await generateGluconFacts({
                coveredFrom,
                coveredTo,
              });
              if (!r.ok) {
                setErr(r.error || "事実生成失敗");
                return;
              }
              if (r.draft) {
                setBody(r.draft.body);
                setStatus(r.draft.status);
                setFacts(r.draft.payload?.facts || []);
                if (r.draft.payload?.covered_from)
                  setCoveredFrom(r.draft.payload.covered_from);
                if (r.draft.payload?.covered_to)
                  setCoveredTo(r.draft.payload.covered_to);
              }
              setMsg("① 事実のみ下書きを生成しました");
              router.refresh();
            });
          }}
        >
          {pending ? "生成中…" : "① 事実だけで下書き"}
        </button>
        <button
          type="button"
          className="btn"
          disabled={pending || !facts.length}
          onClick={() => {
            setErr(null);
            setMsg(null);
            start(async () => {
              const r = await generateGluconClarify();
              if (!r.ok) {
                setErr(r.error || "質問生成失敗");
                return;
              }
              if (r.draft) {
                setClarify(r.draft.payload?.clarify || []);
              }
              setMsg("② 確認質問を用意しました");
              router.refresh();
            });
          }}
        >
          ② 質問を出す
        </button>
        <button
          type="button"
          className="btn"
          disabled={pending || !facts.length}
          onClick={() => {
            setErr(null);
            setMsg(null);
            start(async () => {
              if (clarify.length) {
                await saveGluconClarifyAnswers(
                  clarify.map((c) => ({ id: c.id, answer: c.answer })),
                );
              }
              const r = await generateGluconFinal({
                coveredFrom,
                coveredTo,
              });
              if (!r.ok) {
                setErr(r.error || "最終稿生成失敗");
                return;
              }
              if (r.draft) {
                setBody(r.draft.body);
                setStatus(r.draft.status);
              }
              setMsg("③ 最終稿を生成しました（Before/After 込み）");
              router.refresh();
            });
          }}
        >
          ③ 最終稿を生成
        </button>
      </div>

      {facts.length ? (
        <details open={phase === "facts"} style={{ marginTop: "0.75rem" }}>
          <summary style={{ cursor: "pointer" }}>
            事実リスト（{facts.length}）
          </summary>
          <ul style={{ fontSize: "0.82rem", marginTop: "0.35rem" }}>
            {facts.map((f) => (
              <li key={f.id}>
                {f.forResult !== false ? "【成果候補】" : ""}
                {f.resultCandidateTag ? `[${f.resultCandidateTag}] ` : ""}
                {f.text}
                <span className="meta"> — {f.source}</span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      {clarify.length ? (
        <div style={{ marginTop: "0.75rem" }}>
          <strong style={{ fontSize: "0.9rem" }}>② 確認質問（スキップ可）</strong>
          {clarify.map((c, idx) => (
            <div key={c.id} style={{ marginTop: "0.5rem" }}>
              <p style={{ fontSize: "0.85rem", margin: 0 }}>
                {idx + 1}. {c.question}
              </p>
              <textarea
                value={c.answer}
                onChange={(e) => {
                  const v = e.target.value;
                  setClarify((prev) =>
                    prev.map((x) =>
                      x.id === c.id ? { ...x, answer: v } : x,
                    ),
                  );
                }}
                rows={2}
                style={{ width: "100%", fontSize: "0.85rem", marginTop: "0.25rem" }}
                disabled={pending}
                placeholder="回答（空ならその観点は書かない）"
              />
            </div>
          ))}
          <button
            type="button"
            className="btn"
            style={{ marginTop: "0.5rem" }}
            disabled={pending}
            onClick={() => {
              setErr(null);
              start(async () => {
                const r = await saveGluconClarifyAnswers(
                  clarify.map((c) => ({ id: c.id, answer: c.answer })),
                );
                if (!r.ok) {
                  setErr(r.error || "回答保存失敗");
                  return;
                }
                setMsg("回答を保存しました");
                router.refresh();
              });
            }}
          >
            回答を保存
          </button>
        </div>
      ) : null}

      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        rows={16}
        style={{
          width: "100%",
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
          fontSize: "0.85rem",
          lineHeight: 1.45,
          marginTop: "0.75rem",
        }}
        disabled={pending}
        placeholder="成果報告の本文"
      />

      <ResultScoringChecklist body={body} />

      <ConsultPanel
        kind="result"
        body={body}
        consult={payload.consult || []}
        onApplyRevised={setBody}
        pending={pending}
        start={start}
      />

      {err ? <p className="qe-err">{err}</p> : null}
      {msg ? <p className="meta">{msg}</p> : null}

      <DraftActions
        cycle={cycle}
        kind="result"
        body={body}
        status={status}
        setStatus={setStatus}
        pending={pending}
        start={start}
        postError={initial?.post_error}
        coveredFrom={coveredFrom}
        coveredTo={coveredTo}
      />
    </section>
  );
}

export default function GluconReportPanel({
  cycle,
  drafts,
  journals,
  journalSyncedAt,
  memberHeader,
  monthlyDigest,
  lastResultCoverage,
  today,
}: {
  cycle: GluconActiveCycle | null;
  drafts: GluconDraftRow[];
  journals: GluconJournalDay[];
  journalSyncedAt: string | null;
  memberHeader: GluconMemberHeaderStatus;
  monthlyDigest?: GluconMonthlyDigestPreview | null;
  lastResultCoverage?: GluconLastResultCoverage | null;
  today?: string;
}) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [err, setErr] = useState<string | null>(null);

  if (!cycle) {
    return (
      <section className="card">
        <p className="meta">日程が決まると下書き生成が使えます。</p>
        {!memberHeader.ok ? (
          <p className="qe-err">
            会員ヘッダ未設定: {memberHeader.missing.join(", ")}
            。`.env.jarvis_private` に追記し、Vercel Production/Preview にも同名
            env を設定してください。
          </p>
        ) : null}
      </section>
    );
  }

  return (
    <>
      {!memberHeader.ok ? (
        <section className="card">
          <p className="qe-err">
            会員ヘッダが不完全です（不足: {memberHeader.missing.join(", ")}
            ）。成果・活動報告の先頭が「{memberHeader.preview}
            」になります。`.env.jarvis_private` に設定後、Vercel の Production /
            Preview にも入れて再デプロイしてください。
          </p>
        </section>
      ) : null}

      <section className="card">
        <header>
          <span className="lvl">Journal</span>
          <strong>抽出サマリー</strong>
        </header>
        <p className="meta">
          {cycle.journalFrom}〜{cycle.journalTo} ／ {journals.length} 日分
          {journalSyncedAt
            ? ` ／ 最終 sync ${journalSyncedAt}`
            : " ／ 未 sync（Mac で jarvis_glucon_journal_sync.py を実行）"}
        </p>
        {journals.length ? (
          <ul style={{ fontSize: "0.85rem", maxHeight: 180, overflow: "auto" }}>
            {journals.map((j) => (
              <li key={j.recorded_at}>
                <strong>{j.recorded_at}</strong>{" "}
                {(j.keywords || []).slice(0, 4).join(", ")} —{" "}
                {(j.excerpt || "").slice(0, 80)}
                {(j.excerpt || "").length > 80 ? "…" : ""}
              </li>
            ))}
          </ul>
        ) : (
          <p className="meta">
            該当期間の神大家関連抜粋がありません。Journal sync
            後に再試行してください。
          </p>
        )}

        {monthlyDigest ? (
          <details style={{ marginTop: "0.75rem" }}>
            <summary style={{ cursor: "pointer" }}>
              今月の動きプレビュー（やり取り{" "}
              {monthlyDigest.yoritooriCount}／数値{" "}
              {monthlyDigest.metricsCount}／入退去{" "}
              {monthlyDigest.occupancyCount}
              {monthlyDigest.earlyFills?.length
                ? `／早期入居 ${monthlyDigest.earlyFills.filter((f) => f.early).length}`
                : ""}
              ）
            </summary>
            <p className="meta" style={{ marginTop: "0.5rem" }}>
              {monthlyDigest.from}〜{monthlyDigest.to}
              {!monthlyDigest.yoritooriOk
                ? " ／ やり取り取得に問題あり（下書き生成は続行可）"
                : ""}
            </p>
            {monthlyDigest.notices.length ? (
              <ul style={{ fontSize: "0.8rem", color: "var(--muted, #888)" }}>
                {monthlyDigest.notices.slice(0, 5).map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            ) : null}
            {monthlyDigest.earlyFills?.length ? (
              <>
                <h3 style={{ fontSize: "0.9rem", margin: "0.6rem 0 0.25rem" }}>
                  空室→入居日数（成果候補）
                </h3>
                <ul style={{ fontSize: "0.8rem" }}>
                  {monthlyDigest.earlyFills.map((f) => (
                    <li
                      key={`${f.property_name}-${f.room}-${f.occupied_on}`}
                    >
                      {f.property_name} {f.room}: {f.days}日
                      {f.early ? "（早期）" : ""}
                    </li>
                  ))}
                </ul>
              </>
            ) : null}
            <h3 style={{ fontSize: "0.9rem", margin: "0.6rem 0 0.25rem" }}>
              パートナーやり取り
            </h3>
            <pre
              style={{
                whiteSpace: "pre-wrap",
                fontSize: "0.78rem",
                maxHeight: 160,
                overflow: "auto",
              }}
            >
              {monthlyDigest.yoritooriText}
            </pre>
            <h3 style={{ fontSize: "0.9rem", margin: "0.6rem 0 0.25rem" }}>
              モチベーション数値
            </h3>
            <pre
              style={{
                whiteSpace: "pre-wrap",
                fontSize: "0.78rem",
                maxHeight: 120,
                overflow: "auto",
              }}
            >
              {monthlyDigest.metricsText}
            </pre>
            <h3 style={{ fontSize: "0.9rem", margin: "0.6rem 0 0.25rem" }}>
              入居・空室イベント
            </h3>
            <pre
              style={{
                whiteSpace: "pre-wrap",
                fontSize: "0.78rem",
                maxHeight: 120,
                overflow: "auto",
              }}
            >
              {monthlyDigest.occupancyText}
            </pre>
          </details>
        ) : null}

        <div className="qe-form-actions">
          <button
            type="button"
            className="btn"
            disabled={pending}
            onClick={() => {
              setErr(null);
              start(async () => {
                const r = await generateGluconDrafts();
                if (!r.ok) {
                  setErr(r.error || "生成失敗");
                  return;
                }
                router.refresh();
              });
            }}
          >
            {pending ? "生成中…" : "一括生成（成果優先→活動）"}
          </button>
        </div>
        {err ? <p className="qe-err">{err}</p> : null}
        <p className="meta">
          成果報告は下のステップ（①事実→②質問→③最終稿）が本線。一括は従来互換です。
          <br />
          コマンド例:{" "}
          <code>
            cd ~/git-repos && ~/selenium_env/venv/bin/python
            scripts/jarvis_glucon_journal_sync.py
          </code>
        </p>
      </section>

      <ResultEditor
        cycle={cycle}
        initial={draftFor(drafts, "result")}
        lastResultCoverage={lastResultCoverage}
        today={today || todayYmdClient()}
      />
      <ActivityEditor cycle={cycle} initial={draftFor(drafts, "activity")} />
    </>
  );
}
