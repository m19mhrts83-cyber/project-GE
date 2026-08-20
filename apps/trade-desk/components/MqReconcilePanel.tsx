"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { fmtMqMan, fmtMqManSigned } from "@/lib/mqUnits";
import type { ReconcileDiff } from "@/lib/mqCashflowProject";

type ProjectSummary = {
  annual: {
    pq: number;
    vq: number;
    f: number;
    f_annual: number;
    cash_in: number;
    cash_out: number;
    cash_end: number | null;
    cash_begin: number | null;
  };
  computed: { g: number; equationOk: boolean };
  loanRepaymentMan: number;
  loanExcludedFromG: boolean;
};

type Props = {
  year: string;
  entity: "personal" | "corporate";
  businessLine?: string;
  project: ProjectSummary;
  diffs: ReconcileDiff[];
  factsCount: number;
  bsAsOf: string | null;
  bsSource: string | null;
};

function deltaCell(v: number | null): string {
  if (v == null) return "—";
  if (Math.abs(v) < 0.5) return "0";
  return fmtMqManSigned(v);
}

export default function MqReconcilePanel(props: Props) {
  const {
    year,
    entity,
    businessLine = "realestate",
    project,
    diffs,
    factsCount,
    bsAsOf,
    bsSource,
  } = props;
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [applyBs, setApplyBs] = useState(true);

  const mismatch = diffs.some(
    (d) =>
      (d.deltaFacts != null && Math.abs(d.deltaFacts) >= 1) ||
      (d.deltaBs != null && Math.abs(d.deltaBs) >= 1)
  );

  async function apply() {
    const ok = window.confirm(
      `${year}年の資金繰りを MQ会計表${applyBs ? "と軽量B/S" : ""}に反映します。\n手入力（source=manual）の月はスキップします。よろしいですか？`
    );
    if (!ok) return;
    setBusy(true);
    setMsg(null);
    try {
      const res = await fetch("/api/mq/cashflow/project/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          year: Number(year),
          entity,
          businessLine,
          applyBs,
          confirm: true,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "反映に失敗しました");
      setMsg(
        `反映しました（facts ${data.upserted}ヶ月 · 手入力スキップ ${data.skippedManual} · B/S ${data.bsApplied ? "更新" : "スキップ"}）`
      );
      router.refresh();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card mq-reconcile-card">
      <header>
        <span className="lvl">整合</span>
        <strong>
          {year}年 · 資金繰り（正本） vs MQ / B/S
        </strong>
      </header>
      <p className="meta" style={{ marginTop: 8 }}>
        資金繰り表の金額を起点に、MQ会計表・軽量B/Sへ投影します。ズレたら資金繰り側（列の再分類・期末入力）を直します。
        facts {factsCount}ヶ月
        {bsAsOf ? ` · B/S ${String(bsAsOf).slice(0, 10)}（${bsSource || "—"}）` : " · B/Sなし"}
      </p>
      <p className="meta">
        企業方程式: {project.computed.equationOk ? "✅ 一致" : "⚠️ 不一致"}
        {" · "}ローン元本は G に
        {project.loanExcludedFromG ? "入れていません" : "混入の疑い"}
        （返済 {fmtMqMan(project.loanRepaymentMan)}）
      </p>

      <div className="mq-cashflow-scroll" style={{ marginTop: 10 }}>
        <table className="mq-table">
          <thead>
            <tr>
              <th>項目</th>
              <th className="num">資金繰り</th>
              <th className="num">MQ facts</th>
              <th className="num">B/S</th>
              <th className="num">差（facts）</th>
              <th className="num">差（B/S）</th>
            </tr>
          </thead>
          <tbody>
            {diffs.map((d) => (
              <tr key={d.key}>
                <td>{d.label}</td>
                <td className="num">
                  {d.cashflow == null ? "—" : fmtMqMan(d.cashflow)}
                </td>
                <td className="num">
                  {d.facts == null ? "—" : fmtMqMan(d.facts)}
                </td>
                <td className="num">{d.bs == null ? "—" : fmtMqMan(d.bs)}</td>
                <td className="num">{deltaCell(d.deltaFacts)}</td>
                <td className="num">{deltaCell(d.deltaBs)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {mismatch ? (
        <p className="meta" style={{ color: "var(--high)", marginTop: 8 }}>
          差分があります。資金繰りを直すか、下の反映で MQ/B/S を資金繰りに合わせます。
        </p>
      ) : (
        <p className="meta" style={{ marginTop: 8 }}>
          大きな差分はありません（1万円未満は 0 扱い）。
        </p>
      )}

      <label className="mq-cashflow-reclassify-learn" style={{ marginTop: 10 }}>
        <input
          type="checkbox"
          checked={applyBs}
          onChange={(e) => setApplyBs(e.target.checked)}
        />
        軽量 B/S も更新する
      </label>
      <div style={{ marginTop: 10 }}>
        <button type="button" className="btn primary" disabled={busy} onClick={apply}>
          {busy ? "反映中…" : "資金繰りを MQ / B/S に反映"}
        </button>
      </div>
      {msg ? <p className="meta" style={{ marginTop: 8 }}>{msg}</p> : null}
    </div>
  );
}
