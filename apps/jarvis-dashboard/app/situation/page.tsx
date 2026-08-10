import Link from "next/link";
import Shell from "@/components/Shell";
import WatchAckAllButton from "@/components/WatchAckAllButton";
import WatchHashFocus from "@/components/WatchHashFocus";
import WatchSituationCard from "@/components/WatchSituationCard";
import { watchSortKey } from "@/lib/homeLevels";
import {
  isOpsEphemeralId,
  opsWatchVisibleOnSituation,
} from "@/lib/opsWatch";
import { canShowGenericAckButton } from "@/lib/watchUserAck";
import { createClient } from "@/lib/supabase/server";
import type { WatchCommentRow } from "@/components/WatchCommentThread";

type ActionItem = {
  date?: string;
  shop?: string;
  amount?: number;
  proposal?: string;
  line?: string;
  kind?: string;
};

function readActions(payload: unknown): ActionItem[] {
  if (!payload || typeof payload !== "object") return [];
  const actions = (payload as { actions?: unknown }).actions;
  if (!Array.isArray(actions)) return [];
  return actions.filter((a) => a && typeof a === "object") as ActionItem[];
}

export default async function SituationPage() {
  const supabase = await createClient();
  const { data: items } = await supabase
    .from("watch_status")
    .select("*")
    .order("updated_at", { ascending: false });

  const active = (items || []).filter((i) => {
    if (i.status !== "active") return false;
    if (isOpsEphemeralId(String(i.id))) {
      return opsWatchVisibleOnSituation(i);
    }
    return true;
  });
  const archivedCount = (items || []).filter((i) => i.status === "archived")
    .length;
  active.sort((a, b) => {
    const pa =
      a.payload && typeof a.payload === "object"
        ? (a.payload as Record<string, unknown>)
        : {};
    const pb =
      b.payload && typeof b.payload === "object"
        ? (b.payload as Record<string, unknown>)
        : {};
    const pinA =
      (pa.pin_top === true || a.id === "cursor_pro_plus_downgrade") &&
      a.level !== "ok";
    const pinB =
      (pb.pin_top === true || b.id === "cursor_pro_plus_downgrade") &&
      b.level !== "ok";
    if (pinA !== pinB) return pinA ? -1 : 1;
    return watchSortKey(a.level) - watchSortKey(b.level);
  });

  const ids = active.map((i) => i.id);
  const commentsByWatch = new Map<string, WatchCommentRow[]>();
  if (ids.length) {
    const { data: comments } = await supabase
      .from("watch_comments")
      .select("id,watch_id,role,body,created_at")
      .in("watch_id", ids)
      .order("created_at", { ascending: true });
    for (const c of comments || []) {
      const list = commentsByWatch.get(c.watch_id) || [];
      list.push({
        id: c.id,
        role: c.role,
        body: c.body,
        created_at: c.created_at,
      });
      commentsByWatch.set(c.watch_id, list);
    }
  }

  return (
    <Shell active="/situation">
      <WatchHashFocus />
      <h1>状況ウォッチ</h1>
      <p className="sub">
        気にしている項目（3段階: 要確認／注意／参考）。各項目は折りたたみ表示です（タップで詳細・確認・聞くを展開）。
        「確認した」でナビ／ホームのバッジを一時的に消せます（既定7日、または状況が変わると再表示）。
        復元は{" "}
        <Link href="/archive" style={{ color: "var(--accent)", fontWeight: 600 }}>
          アーカイブ
        </Link>
        から。
      </p>
      <div className="stats">
        <div className="stat">
          アクティブ <strong>{active.length}</strong>
        </div>
        <div className="stat">
          アーカイブ{" "}
          <strong>
            <Link href="/archive" style={{ color: "inherit" }}>
              {archivedCount}
            </Link>
          </strong>
        </div>
      </div>
      <WatchAckAllButton
        count={active.filter((it) => {
          const pl =
            it.payload && typeof it.payload === "object"
              ? (it.payload as Record<string, unknown>)
              : {};
          return canShowGenericAckButton({
            id: String(it.id),
            level: it.level,
            summary: it.summary,
            status: it.status,
            payload: pl,
          });
        }).length}
      />
      <h2>アクティブ</h2>
      {active.length === 0 ? (
        <p className="empty">まだ push されていません</p>
      ) : (
        active.map((it) => {
          const pl =
            it.payload && typeof it.payload === "object"
              ? (it.payload as Record<string, unknown>)
              : {};
          const neverArchive = Boolean(
            pl.never_archive || isOpsEphemeralId(String(it.id)),
          );
          const showOpsAck =
            it.id === "ops_fix_notice" && pl.show_banner === true;
          return (
            <WatchSituationCard
              key={it.id}
              id={String(it.id)}
              title={it.title || String(it.id)}
              level={it.level || "info"}
              summary={it.summary}
              detail={it.detail}
              source={it.source}
              status={it.status}
              cursorPrompt={it.cursor_prompt}
              payload={pl}
              actions={readActions(it.payload)}
              comments={commentsByWatch.get(it.id) || []}
              neverArchive={neverArchive}
              showOpsAck={showOpsAck}
            />
          );
        })
      )}
      <p className="sub" style={{ marginTop: 24 }}>
        <Link href="/archive" className="btn">
          アーカイブを見る →
        </Link>
      </p>
    </Shell>
  );
}
