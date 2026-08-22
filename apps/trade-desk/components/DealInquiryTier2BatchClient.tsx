"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { BAIRITSU_MARKER } from "@/lib/reInquiryShared";

type QueueItem = {
  deal_id: string;
  title: string;
  match_score: number | null;
  area: string | null;
  to: string;
  subject: string;
  body: string;
  body_preview: string;
  land_method_bairitsu: boolean;
  badges: string[];
};

type QueueResponse = {
  enabled: boolean;
  daily_cap: number;
  sent_today: number;
  remaining: number;
  queue: QueueItem[];
  error?: string;
};

async function sha256Hex(text: string): Promise<string> {
  const data = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export default function DealInquiryTier2BatchClient() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<QueueResponse | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setMsg(null);
    try {
      const res = await fetch("/api/re/inquiry-tier2-queue");
      const json = (await res.json()) as QueueResponse;
      if (!res.ok) {
        setMsg(json.error || "読込失敗");
        setData(null);
        return;
      }
      setData(json);
      setSelected(new Set(json.queue.map((q) => q.deal_id)));
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "エラー");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function sendBatch() {
    if (!data || !checked) {
      setMsg("一括確認チェックを入れてください");
      return;
    }
    const items = data.queue.filter((q) => selected.has(q.deal_id));
    if (items.length === 0) {
      setMsg("送信する案件を選択してください");
      return;
    }
    if (items.length > data.remaining) {
      setMsg(`本日残り ${data.remaining} 件までです`);
      return;
    }
    for (const q of items) {
      if (q.land_method_bairitsu && !q.body.includes(BAIRITSU_MARKER)) {
        setMsg(`倍率地域: ${q.title.slice(0, 30)} — 固定資産税依頼文が不足`);
        return;
      }
    }

    setBusy(true);
    setMsg(null);
    try {
      const payloadItems = await Promise.all(
        items.map(async (q) => ({
          deal_id: q.deal_id,
          to: q.to,
          subject: q.subject,
          body: q.body,
          confirm_snapshot: {
            to: q.to,
            subject: q.subject,
            body_sha256: await sha256Hex(q.body),
          },
        }))
      );
      const res = await fetch("/api/re/inquiry-tier2-send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ui_confirmed: true,
          items: payloadItems,
        }),
      });
      const out = await res.json();
      if (!res.ok) {
        setMsg(out.error || "送信失敗");
        if (out.errors?.length) setMsg(`${out.error}\n${out.errors.join("\n")}`);
        return;
      }
      setMsg(`${out.enqueued} 件を送信キューに入れました（Mac worker が estate から送信）`);
      setChecked(false);
      router.refresh();
      await load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "エラー");
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return <p className="meta">読込中…</p>;
  }

  if (!data?.enabled) {
    return (
      <div className="card" style={{ padding: 16 }}>
        <p>Tier2 日次キューは現在 OFF です。</p>
        <p className="meta">
          有効化: <code>config/kurashift_re_inquiry_auto.yaml</code> の{" "}
          <code>tier2_daily_queue.enabled: true</code>
        </p>
        <Link href="/realestate/deals?tab=candidates" className="btn">
          候補一覧へ
        </Link>
      </div>
    );
  }

  return (
    <div>
      <div className="card" style={{ marginBottom: 16, padding: 16 }}>
        <p className="meta">
          条件: Grok「聞く」+ スコア≥5 + HZ除外 · 宛先あり · From=estate
        </p>
        <p style={{ marginTop: 8 }}>
          本日 <strong>{data.sent_today}</strong> / {data.daily_cap} 件送信済 ·
          残り <strong>{data.remaining}</strong> 件
        </p>
        <p className="meta" style={{ marginTop: 8 }}>
          送信待ち <strong>{data.queue.length}</strong> 件（上限内）
        </p>
      </div>

      {data.queue.length === 0 ? (
        <div className="card" style={{ padding: 16 }}>
          <p>いま Tier2 対象はありません。</p>
          <p className="meta" style={{ marginTop: 8 }}>
            Tier1 の「問合せ候補」から個別送信するか、Grok 調査後に再度確認してください。
          </p>
          <Link
            href="/realestate/deals?tab=candidates&inquiry=ready"
            className="btn"
            style={{ marginTop: 12, display: "inline-block" }}
          >
            問合せ候補一覧
          </Link>
        </div>
      ) : (
        <>
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th></th>
                  <th>スコア</th>
                  <th>物件</th>
                  <th>宛先</th>
                  <th>件名</th>
                  <th>本文</th>
                </tr>
              </thead>
              <tbody>
                {data.queue.map((q) => (
                  <tr key={q.deal_id}>
                    <td>
                      <input
                        type="checkbox"
                        checked={selected.has(q.deal_id)}
                        onChange={() => toggle(q.deal_id)}
                        disabled={busy || data.remaining <= 0}
                      />
                    </td>
                    <td className="meta">{q.match_score ?? "—"}</td>
                    <td>
                      {q.title.slice(0, 48)}
                      {q.badges?.length ? (
                        <div className="meta">{q.badges.join(" · ")}</div>
                      ) : null}
                    </td>
                    <td className="meta" style={{ fontSize: 11 }}>
                      {q.to}
                    </td>
                    <td className="meta" style={{ fontSize: 11 }}>
                      {q.subject.slice(0, 40)}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="btn"
                        style={{ fontSize: 11, padding: "2px 6px" }}
                        onClick={() =>
                          setExpanded(expanded === q.deal_id ? null : q.deal_id)
                        }
                      >
                        {expanded === q.deal_id ? "閉じる" : "表示"}
                      </button>
                      {expanded === q.deal_id ? (
                        <pre
                          className="meta"
                          style={{
                            whiteSpace: "pre-wrap",
                            fontSize: 10,
                            maxWidth: 360,
                            marginTop: 4,
                          }}
                        >
                          {q.body}
                        </pre>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="card" style={{ marginTop: 16, padding: 16 }}>
            <label
              className="meta"
              style={{ display: "flex", gap: 8, alignItems: "flex-start" }}
            >
              <input
                type="checkbox"
                checked={checked}
                onChange={(e) => setChecked(e.target.checked)}
                disabled={busy}
              />
              <span>
                選択した {selected.size}{" "}
                件すべて、プレビュー内容で estate から第一問合せを送ってよい（一括確認）
              </span>
            </label>
            {msg ? (
              <p
                className="meta"
                style={{
                  marginTop: 12,
                  color: msg.includes("キューに") ? "#047857" : "#b91c1c",
                  whiteSpace: "pre-wrap",
                }}
              >
                {msg}
              </p>
            ) : null}
            <div style={{ marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button
                type="button"
                className="btn"
                disabled={
                  busy ||
                  !checked ||
                  selected.size === 0 ||
                  data.remaining <= 0
                }
                onClick={() => void sendBatch()}
              >
                {busy
                  ? "送信中…"
                  : `${Math.min(selected.size, data.remaining)} 件を送信キューへ`}
              </button>
              <Link href="/realestate/deals?tab=candidates" className="btn">
                候補一覧
              </Link>
              <Link href="/jobs" className="btn">
                ジョブ確認
              </Link>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
