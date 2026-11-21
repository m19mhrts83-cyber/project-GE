import { createServiceClient } from "@/lib/supabase/admin";
import {
  RESULT_LABEL,
  STALL_LABEL,
  STALL_SIGNAL,
  ageText,
  isStallReportOld,
  parseStallReport,
  sortStallRows,
  type StallReport,
} from "@/lib/stallWatch315b";

/**
 * /agent-team「週次稼働」タブの先頭: 315-B 300番台 停止・空回り（毎日 08:20・18:20）。
 * 見る順: ① 結果（成功／部分成功／失敗）と件数 → ② 異常の社員だけカード → ③ 正常も含む全体は押して開く。
 */

const CLS = { "🟢": "g", "🟡": "y", "🔴": "r" } as const;

async function loadStallReport(): Promise<{ report: StallReport | null; error?: string }> {
  const sb = createServiceClient();
  if (!sb) return { report: null, error: "Supabase 未設定" };
  const meta = await sb.from("sync_meta").select("value").eq("key", "stall_watch_315b").maybeSingle();
  if (meta.error) return { report: null, error: meta.error.message };
  return { report: parseStallReport(meta.data?.value) };
}

function hm(iso: string): string {
  const d = new Date(Date.parse(iso) + 9 * 3600_000);
  if (Number.isNaN(d.getTime())) return "—";
  return `${d.getUTCMonth() + 1}/${d.getUTCDate()} ${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;
}

export default async function StallWatchSection() {
  const { report, error } = await loadStallReport();
  if (!report) {
    return (
      <p className="meta">
        300番台 停止・空回り（315-B）: {error ? `記録を読めませんでした（${error}）` : "まだ記録がありません（毎日 08:20・18:20 に更新）"}
      </p>
    );
  }
  const rows = sortStallRows(report.rows);
  const bad = rows.filter((r) => r.status !== "ok");
  const old = isStallReportOld(report);
  return (
    <>
      <h3 className="mx-h">
        300番台 停止・空回り <span>315-B · {hm(report.checked_at)} 点検 · {RESULT_LABEL[report.result]}</span>
      </h3>
      {old ? <p className="meta">⚠️ 監視の更新が止まっています（最終 {hm(report.checked_at)}）。下の判定は古い可能性があります。</p> : null}
      {bad.length ? (
        <ul className="wa-next">
          {bad.map((r) => (
            <li key={r.id} className={`s-${CLS[STALL_SIGNAL[r.status]]}`}>
              <b>
                {STALL_SIGNAL[r.status]} {r.label} — {STALL_LABEL[r.status]}
              </b>
              <span>{r.why}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="meta">🟢 {rows.length} 件とも正常（止まり・空回りなし）</p>
      )}
      <details className="mat-rule">
        <summary>
          全体（{rows.length}）{report.result_why.length ? ` · 注意 ${report.result_why.length}` : ""}
        </summary>
        <ul className="meta">
          {rows.map((r) => (
            <li key={r.id}>
              {STALL_SIGNAL[r.status]} {r.label}: 最終 {ageText(r.age_h)}（上限 {r.max_age_h ?? "—"}h）
              {r.idle_why ? ` · 空回り: ${r.idle_why}` : ""}
            </li>
          ))}
          {report.result_why.map((w) => (
            <li key={w}>⚠️ {w}</li>
          ))}
          <li>
            結果の保存: {report.save?.ok ? "成功" : "失敗"} · 画面反映: この表示の回は成功 · 今回の通知対象 {report.pending.length} 件 · run_id {report.run_id}
          </li>
        </ul>
      </details>
    </>
  );
}
