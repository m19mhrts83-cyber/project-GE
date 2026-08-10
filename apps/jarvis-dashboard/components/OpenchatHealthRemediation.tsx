"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import CopyPathButton from "@/components/CopyPathButton";
import WatchCommentThread, {
  type WatchCommentRow,
} from "@/components/WatchCommentThread";
import { queueOpenchatMacRecover } from "@/app/actions/openchatRecover";

export type MacRecipe = {
  id?: string;
  route_ids?: string[];
  label?: string;
  status?: string;
  error?: string;
  requested_at?: string;
  finished_at?: string;
  result?: string;
};

export type Remediation = {
  symptom?: string;
  route_attention_count?: number;
  infra_attention?: boolean;
  infra_symptoms?: string[];
  main_stale?: boolean;
  cursor_prompt?: string;
  mac_recipe?: MacRecipe | null;
  hint?: string;
};

export default function OpenchatHealthRemediation({
  show,
  remediation,
  watchId = "openchat_threads",
  title,
  summary,
  detail,
  cursorPrompt,
  payload,
  comments,
}: {
  show: boolean;
  remediation: Remediation | null;
  watchId?: string;
  title: string;
  summary: string;
  detail?: string | null;
  cursorPrompt?: string | null;
  payload?: Record<string, unknown> | null;
  comments: WatchCommentRow[];
}) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);

  if (!show) return null;

  const rem = remediation || {};
  const prompt =
    rem.cursor_prompt ||
    cursorPrompt ||
    "ダッシュボード /openchat/health を確認してください。";
  const recipe = rem.mac_recipe;
  const canQueue =
    recipe &&
    recipe.id === "openchat_init_bootstrap" &&
    Array.isArray(recipe.route_ids) &&
    recipe.route_ids.length > 0 &&
    !["queued", "running"].includes(String(recipe.status || ""));

  return (
    <section className="openchat-remediation" aria-label="解消パネル">
      <h2>解消に走る</h2>
      {rem.hint ? <p className="meta">{rem.hint}</p> : null}
      <p className="sub" style={{ marginTop: 4 }}>
        診断・方針は「聞く」（Cloud 本線）。CHRLINE／QR／バックフィルは Mac
        専用です。メイン全体が止まっているときはスレ bootstrap
        より取込経路を先に。
      </p>
      <div className="openchat-remediation-actions">
        <CopyPathButton path={prompt} label="Cursorプロンプトをコピー" />
        {canQueue ? (
          <button
            type="button"
            className="btn"
            disabled={pending}
            onClick={() => setConfirmOpen(true)}
          >
            Macで既知復旧を実行
          </button>
        ) : null}
        {recipe?.status === "queued" || recipe?.status === "running" ? (
          <span className="badge lvl-warn">
            Mac復旧 {recipe.status}
            {recipe.route_ids?.length
              ? `（${recipe.route_ids.length}ルート）`
              : ""}
          </span>
        ) : null}
        {recipe?.status === "done" ? (
          <span className="badge lvl-ok">
            Mac復旧完了 {recipe.result ? `· ${recipe.result}` : ""}
          </span>
        ) : null}
        {recipe?.status === "error" ? (
          <span className="badge lvl-attention">
            Mac復旧エラー: {recipe.error || "詳細はログ"}
          </span>
        ) : null}
      </div>
      {err ? <p className="err">{err}</p> : null}
      {msg ? <p className="meta">{msg}</p> : null}

      {confirmOpen ? (
        <div className="openchat-remediation-confirm" role="dialog">
          <p>
            次のルートで pause → --init discover → backfill → resume
            を Mac で実行します。よろしいですか？
          </p>
          <pre className="watch-detail">
            {(recipe?.route_ids || []).join("\n")}
          </pre>
          <div className="openchat-remediation-actions">
            <button
              type="button"
              className="btn"
              disabled={pending}
              onClick={() => {
                setErr(null);
                setMsg(null);
                start(async () => {
                  const r = await queueOpenchatMacRecover({
                    routeIds: recipe?.route_ids || [],
                  });
                  if (!r.ok) {
                    setErr(r.error || "キュー登録に失敗しました");
                    return;
                  }
                  setMsg(r.message || "Mac 復旧キューに入れました");
                  setConfirmOpen(false);
                  router.refresh();
                });
              }}
            >
              実行してよい
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

      <details className="watch-prompt-details" style={{ marginTop: 12 }}>
        <summary>Cursor用プロンプト全文</summary>
        <pre className="watch-detail">{prompt}</pre>
      </details>

      <div style={{ marginTop: 16 }}>
        <h3 style={{ fontSize: "1rem", margin: "0 0 8px" }}>聞く</h3>
        <WatchCommentThread
          watchId={watchId}
          title={title}
          summary={summary}
          detail={detail}
          cursorPrompt={prompt}
          payload={payload}
          comments={comments}
          path="/openchat/health"
        />
      </div>
    </section>
  );
}
