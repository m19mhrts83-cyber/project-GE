"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";
import {
  generateGluconDrafts,
  queueGluconPost,
  saveGluconDraft,
  skipGluconDraft,
} from "@/app/actions/glucon";
import type {
  GluconActiveCycle,
  GluconDraftRow,
  GluconJournalDay,
  GluconReportKind,
} from "@/lib/glucon/types";
import { WESTUDY_FORUM_URLS } from "@/lib/glucon/types";

const KIND_LABEL: Record<GluconReportKind, string> = {
  activity: "活動報告",
  result: "成果報告",
};

function draftFor(
  drafts: GluconDraftRow[],
  kind: GluconReportKind,
): GluconDraftRow | null {
  return drafts.find((d) => d.kind === kind) || null;
}

function DraftEditor({
  cycle,
  kind,
  initial,
}: {
  cycle: GluconActiveCycle;
  kind: GluconReportKind;
  initial: GluconDraftRow | null;
}) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [body, setBody] = useState(initial?.body || "");
  const [status, setStatus] = useState(initial?.status || "draft");
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);

  useEffect(() => {
    setBody(initial?.body || "");
    setStatus(initial?.status || "draft");
  }, [initial?.id, initial?.body, initial?.status, initial?.updated_at]);

  const forumUrl = WESTUDY_FORUM_URLS[kind];

  return (
    <section className="card">
      <header>
        <span className="lvl">{KIND_LABEL[kind]}</span>
        <strong>
          {initial?.title || `${cycle.periodKey} ${KIND_LABEL[kind]}`}
        </strong>
        <span className="meta" style={{ marginLeft: "0.5rem" }}>
          status: {status}
        </span>
      </header>

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
        placeholder={`${KIND_LABEL[kind]}の本文`}
      />

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
              setMsg("保存しました");
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
          disabled={
            pending ||
            !body.trim() ||
            status === "posted" ||
            status === "queued" ||
            status === "skipped" ||
            body.includes("該当する成果報告なし")
          }
          onClick={() => setConfirmOpen(true)}
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

      {initial?.post_error ? (
        <p className="qe-err">投稿エラー: {initial.post_error}</p>
      ) : null}
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
                  const r = await queueGluconPost(cycle.periodKey, kind);
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
    </section>
  );
}

export default function GluconReportPanel({
  cycle,
  drafts,
  journals,
  journalSyncedAt,
}: {
  cycle: GluconActiveCycle | null;
  drafts: GluconDraftRow[];
  journals: GluconJournalDay[];
  journalSyncedAt: string | null;
}) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [err, setErr] = useState<string | null>(null);

  if (!cycle) {
    return (
      <section className="card">
        <p className="meta">日程が決まると下書き生成が使えます。</p>
      </section>
    );
  }

  return (
    <>
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
            該当期間の神大家関連抜粋がありません。Journal sync 後に再試行してください。
          </p>
        )}
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
            {pending ? "生成中…" : "活動・成果の下書きを生成"}
          </button>
        </div>
        {err ? <p className="qe-err">{err}</p> : null}
        <p className="meta">
          コマンド例:{" "}
          <code>
            cd ~/git-repos && python scripts/jarvis_glucon_journal_sync.py
          </code>
        </p>
      </section>

      <DraftEditor
        cycle={cycle}
        kind="activity"
        initial={draftFor(drafts, "activity")}
      />
      <DraftEditor
        cycle={cycle}
        kind="result"
        initial={draftFor(drafts, "result")}
      />
    </>
  );
}
