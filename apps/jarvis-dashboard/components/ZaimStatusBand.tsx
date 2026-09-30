"use client";

import { useState, useTransition } from "react";
import { queueZaimFinanceSync } from "@/app/actions/zaimWatch";

export type BankSyncPayload = {
  level?: string | null;
  summary?: string | null;
  updated_at?: string | null;
  csv_max_date?: string | null;
  ok_n?: number;
  unlinkable_n?: number;
  stale?: Array<{
    label?: string;
    lag_days?: number | null;
    note?: string;
  }>;
  missing?: Array<{ label?: string }>;
};

export type CsvWeeklyPayload = {
  last_ok?: boolean | null;
  last_success_at?: string | null;
  last_error?: string | null;
  updated_at?: string | null;
};

function shortDate(raw: string | null | undefined): string {
  if (!raw) return "—";
  const s = String(raw);
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) return s.slice(0, 10);
  return s.slice(0, 16);
}

function buildStatusLine(
  bank: BankSyncPayload | null,
  csvWeekly: CsvWeeklyPayload | null,
): { line: string; tone: "ok" | "attention" | "warn" } {
  const csvDate = bank?.csv_max_date || null;
  const stale = bank?.stale || [];
  const okN = bank?.ok_n ?? 0;
  const staleN = stale.length;

  let line: string;
  let tone: "ok" | "attention" | "warn" = "ok";

  if (staleN > 0) {
    const top = stale[0];
    const lag = top?.lag_days != null ? `${top.lag_days}日遅れ` : "遅れ";
    const label = top?.label || "口座";
    line = `最終CSV ${shortDate(csvDate)} · 要再接続 ${staleN} · ${label}が${lag} · 口座 OK ${okN}`;
    tone = bank?.level === "warn" ? "warn" : "attention";
  } else if (csvDate) {
    line = `最終CSV ${shortDate(csvDate)} · 口座 OK ${okN} · 遅れなし`;
  } else {
    line = bank?.summary
      ? String(bank.summary)
      : "口座情報未取得（bank_sync_check 待ち）";
    tone = "attention";
  }

  if (csvWeekly && csvWeekly.last_ok === false && csvWeekly.last_error) {
    const err = String(csvWeekly.last_error);
    let macNote = "OneDrive CSV 週次: 要確認";
    if (/session_missing|ログイン切れ|login/i.test(err)) {
      macNote = "OneDrive CSV 週次: 要ログイン";
    } else if (/deadlock|Resource deadlock/i.test(err)) {
      macNote = "OneDrive CSV 週次: 読取デッドロック（再実行可）";
    } else if (/NETWORK_CHANGED|net::ERR/i.test(err)) {
      macNote = "OneDrive CSV 週次: ネットワーク一時障害";
    } else if (/export_failed/i.test(err)) {
      macNote = "OneDrive CSV 週次: エクスポート失敗";
    }
    line = `${line} · ${macNote}`;
    if (tone === "ok") tone = "attention";
  }

  return { line, tone };
}

export default function ZaimStatusBand({
  bank,
  csvWeekly,
  refreshQueued,
  learnLine,
}: {
  bank: BankSyncPayload | null;
  csvWeekly: CsvWeeklyPayload | null;
  refreshQueued?: boolean;
  learnLine?: string | null;
}) {
  const { line, tone } = buildStatusLine(bank, csvWeekly);
  const [msg, setMsg] = useState<string | null>(
    refreshQueued ? "更新キュー済み（完了まで数分）" : null,
  );
  const [pending, start] = useTransition();

  return (
    <section
      className={`card level-${tone === "ok" ? "info" : tone}`}
      style={{ marginBottom: 16 }}
      aria-label="Zaim 鮮度ステータス"
    >
      <header
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          gap: 8,
        }}
      >
        <span className="lvl">鮮度</span>
        <strong style={{ flex: 1, minWidth: 200 }}>{line}</strong>
        <button
          type="button"
          className="btn"
          disabled={pending}
          title="裏でキュー。完了まで数分。開いただけでは走りません"
          onClick={() => {
            start(async () => {
              const r = await queueZaimFinanceSync();
              if (r.ok) {
                setMsg(r.message || "更新をキューしました（完了まで数分）");
              } else {
                setMsg(r.error || "キューに失敗しました");
              }
            });
          }}
        >
          {pending ? "送信中…" : "今すぐ更新"}
        </button>
      </header>
      <p className="meta" style={{ marginTop: 6, marginBottom: 0 }}>
        開いただけでは銀行連携は更新されません。学習は取込のたび自動。違うときだけ「おかしい」。
        {bank?.updated_at ? ` · 口座検知 ${shortDate(bank.updated_at)}` : ""}
        {learnLine ? ` · ${learnLine}` : ""}
      </p>
      {msg ? (
        <p className="meta" style={{ marginTop: 4, marginBottom: 0 }}>
          {msg}
        </p>
      ) : null}
    </section>
  );
}
