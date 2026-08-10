"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";
import {
  analyzeGluconResultBody,
  generateGluconDrafts,
  queueGluconPost,
  saveGluconDraft,
  skipGluconDraft,
} from "@/app/actions/glucon";
import {
  canQueueGluconDraft,
  isNoResultBody,
} from "@/lib/glucon/postGuard";
import type {
  GluconActiveCycle,
  GluconDraftRow,
  GluconJournalDay,
  GluconMemberHeaderStatus,
  GluconMonthlyDigestPreview,
  GluconReportKind,
  ResultScoringHints,
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
  // skipped でも実内容に書き換えていれば投稿導線を開く（保存で ready になる）
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

      {kind === "result" ? <ResultScoringChecklist body={body} /> : null}

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
  memberHeader,
  monthlyDigest,
}: {
  cycle: GluconActiveCycle | null;
  drafts: GluconDraftRow[];
  journals: GluconJournalDay[];
  journalSyncedAt: string | null;
  memberHeader: GluconMemberHeaderStatus;
  monthlyDigest?: GluconMonthlyDigestPreview | null;
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
              {monthlyDigest.occupancyCount}）
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
            {pending ? "生成中…" : "活動・成果の下書きを生成"}
          </button>
        </div>
        {err ? <p className="qe-err">{err}</p> : null}
        <p className="meta">
          コマンド例:{" "}
          <code>
            cd ~/git-repos && ~/selenium_env/venv/bin/python
            scripts/jarvis_glucon_journal_sync.py
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
