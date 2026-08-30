"use client";

import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import type { CleanupReason } from "@/lib/reDealCleanup";

type Candidate = {
  id: string;
  title: string;
  area: string | null;
  match_score: number | null;
  updated_at: string | null;
  age_days: number;
  reasons: CleanupReason[];
  default_checked: boolean;
};

type PreviewResponse = {
  ok?: boolean;
  error?: string;
  stale_days?: number;
  max_per_batch?: number;
  reason_labels?: Record<string, string>;
  candidates?: Candidate[];
  count?: number;
};

type ApplyResponse = {
  ok?: boolean;
  error?: string;
  batch_id?: string;
  applied_count?: number;
  skipped?: { id: string; reason: string }[];
};

export default function DealCleanupPanel() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [reasonLabels, setReasonLabels] = useState<Record<string, string>>({});
  const [staleDays, setStaleDays] = useState(30);
  const [maxBatch, setMaxBatch] = useState(20);
  const [lastBatchId, setLastBatchId] = useState<string | null>(null);

  const loadPreview = useCallback(async () => {
    setLoading(true);
    setMsg(null);
    try {
      const res = await fetch("/api/re/deals/cleanup");
      const json = (await res.json()) as PreviewResponse;
      if (!res.ok) {
        setMsg(json.error || "読込失敗");
        setCandidates([]);
        return;
      }
      const list = json.candidates || [];
      setCandidates(list);
      setReasonLabels(json.reason_labels || {});
      setStaleDays(json.stale_days ?? 30);
      setMaxBatch(json.max_per_batch ?? 20);
      setSelected(
        new Set(list.filter((c) => c.default_checked).map((c) => c.id))
      );
      setOpen(true);
      if (list.length === 0) {
        setMsg("いま整理候補はありません（低スコア・エリア外・放置のみ対象）");
      }
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "エラー");
    } finally {
      setLoading(false);
    }
  }, []);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function selectAll(on: boolean) {
    if (on) setSelected(new Set(candidates.map((c) => c.id)));
    else setSelected(new Set());
  }

  async function apply() {
    const ids = [...selected];
    if (ids.length === 0) {
      setMsg("1件以上チェックしてください");
      return;
    }
    if (
      !window.confirm(
        `${ids.length}件を見送り（候補から外す）にします。よろしいですか？`
      )
    ) {
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      const res = await fetch("/api/re/deals/cleanup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "apply", deal_ids: ids }),
      });
      const json = (await res.json()) as ApplyResponse;
      if (!res.ok) {
        setMsg(json.error || "失敗しました");
        return;
      }
      setLastBatchId(json.batch_id || null);
      setMsg(
        `${json.applied_count ?? 0}件を見送りにしました（24時間以内なら戻せます）`
      );
      setCandidates([]);
      setSelected(new Set());
      setOpen(false);
      router.refresh();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "エラー");
    } finally {
      setBusy(false);
    }
  }

  async function undo() {
    if (!lastBatchId) return;
    if (!window.confirm("直前の一括整理を戻しますか？")) return;
    setBusy(true);
    setMsg(null);
    try {
      const res = await fetch("/api/re/deals/cleanup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "undo", batch_id: lastBatchId }),
      });
      const json = (await res.json()) as ApplyResponse & {
        restored_count?: number;
      };
      if (!res.ok) {
        setMsg(json.error || "戻しに失敗しました");
        return;
      }
      setMsg(`${json.restored_count ?? 0}件を候補に戻しました`);
      setLastBatchId(null);
      router.refresh();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "エラー");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <header>
        <span className="lvl">整理</span>
        <strong>候補の一括整理</strong>
      </header>
      <p className="meta" style={{ marginTop: 8 }}>
        低スコア・エリア外・{staleDays}日以上放置の候補をまとめて見送りにできます。
        問合せ進行中・進行中フォロー・Grok「聞く」・内見以降は対象外。1回最大{" "}
        {maxBatch}件。
      </p>
      <div style={{ marginTop: 10, display: "flex", flexWrap: "wrap", gap: 8 }}>
        <button
          type="button"
          className="btn"
          disabled={loading || busy}
          onClick={() => void loadPreview()}
        >
          {loading ? "読込中…" : "整理候補を出す"}
        </button>
        {lastBatchId ? (
          <button
            type="button"
            className="btn"
            disabled={busy}
            onClick={() => void undo()}
          >
            {busy ? "…" : "この整理を戻す"}
          </button>
        ) : null}
      </div>
      {msg ? (
        <p className="meta" style={{ marginTop: 8 }}>
          {msg}
        </p>
      ) : null}

      {open && candidates.length > 0 ? (
        <div style={{ marginTop: 12 }}>
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: 8,
              alignItems: "center",
              marginBottom: 8,
            }}
          >
            <label className="meta" style={{ display: "flex", gap: 6 }}>
              <input
                type="checkbox"
                checked={
                  candidates.length > 0 && selected.size === candidates.length
                }
                onChange={(e) => selectAll(e.target.checked)}
                disabled={busy}
              />
              すべて（{selected.size}/{candidates.length}）
            </label>
            <button
              type="button"
              className="btn"
              disabled={busy || selected.size === 0}
              onClick={() => void apply()}
            >
              {busy ? "処理中…" : `${selected.size}件を見送りにする`}
            </button>
            <button
              type="button"
              className="btn"
              disabled={busy}
              onClick={() => {
                setOpen(false);
                setCandidates([]);
              }}
            >
              閉じる
            </button>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th></th>
                  <th>スコア</th>
                  <th>物件</th>
                  <th>エリア</th>
                  <th>経過</th>
                  <th>理由</th>
                </tr>
              </thead>
              <tbody>
                {candidates.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <input
                        type="checkbox"
                        checked={selected.has(c.id)}
                        onChange={() => toggle(c.id)}
                        disabled={busy}
                      />
                    </td>
                    <td className="meta">{c.match_score ?? "—"}</td>
                    <td style={{ fontSize: 13 }}>{c.title.slice(0, 56)}</td>
                    <td className="meta">{c.area || "—"}</td>
                    <td className="meta">{c.age_days}日</td>
                    <td className="meta" style={{ fontSize: 11 }}>
                      {c.reasons
                        .map((r) => reasonLabels[r] || r)
                        .join(" · ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  );
}
