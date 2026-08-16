"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { computeMq, formatRatio } from "@/lib/mqEquations";
import { fmtMqMan } from "@/lib/mqUnits";
import { qFieldLabel } from "@/lib/mqPolicy";

type Props = {
  defaultLine: "realestate" | "ai";
  defaultEntity: "personal" | "corporate";
  defaultMonth: string;
};

export default function MqFactsForm({
  defaultLine,
  defaultEntity,
  defaultMonth,
}: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [pq, setPq] = useState("");
  const [vq, setVq] = useState("");
  const [f, setF] = useState("");
  const [fAnnual, setFAnnual] = useState("");
  const [q, setQ] = useState("");

  const preview = useMemo(() => {
    const fEff =
      (Number(f) || 0) + (Number(fAnnual) || 0) / 12;
    return computeMq({
      pq: Number(pq) || 0,
      vq: Number(vq) || 0,
      f: fEff,
      q: q === "" ? null : Number(q),
    });
  }, [pq, vq, f, fAnnual, q]);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    const fd = new FormData(e.currentTarget);
    const body = {
      business_line: String(fd.get("business_line")),
      entity: String(fd.get("entity")),
      period_month: String(fd.get("period_month")),
      scenario_kind: "actual",
      q: fd.get("q") === "" ? null : fd.get("q"),
      pq: fd.get("pq"),
      vq: fd.get("vq"),
      f: fd.get("f"),
      f_annual: fd.get("f_annual") === "" ? 0 : fd.get("f_annual"),
      cash_in: fd.get("cash_in") === "" ? null : fd.get("cash_in"),
      cash_out: fd.get("cash_out") === "" ? null : fd.get("cash_out"),
      cash_end: fd.get("cash_end") === "" ? null : fd.get("cash_end"),
      depreciation_jpy:
        fd.get("depreciation_jpy") === "" ? null : fd.get("depreciation_jpy"),
      note: fd.get("note") || null,
      source: "manual",
    };
    try {
      const res = await fetch("/api/mq/facts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        setMsg(String(json.error || `HTTP ${res.status}`));
        return;
      }
      setMsg("保存しました");
      router.refresh();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "保存に失敗");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="tax-metrics-form">
      <div className="tax-form-row">
        <label>
          事業線
          <select name="business_line" defaultValue={defaultLine}>
            <option value="realestate">不動産</option>
            <option value="ai">AI</option>
          </select>
        </label>
        <label>
          主体
          <select name="entity" defaultValue={defaultEntity}>
            <option value="personal">個人</option>
            <option value="corporate">法人</option>
          </select>
        </label>
        <label>
          月（YYYY-MM）
          <input
            name="period_month"
            type="month"
            defaultValue={defaultMonth}
            required
          />
        </label>
      </div>
      <div className="tax-form-row">
        <label>
          {qFieldLabel(defaultLine)}
          <input
            name="q"
            type="number"
            step="any"
            value={q}
            onChange={(ev) => setQ(ev.target.value)}
            placeholder={
              defaultLine === "ai"
                ? "案件数（未入力可）"
                : "稼働戸月（未入力可・単価は —）"
            }
          />
        </label>
        <label>
          PQ（売上・万円）
          <input
            name="pq"
            type="number"
            step="1"
            required
            value={pq}
            onChange={(ev) => setPq(ev.target.value)}
          />
        </label>
        <label>
          VQ（変動費・万円）
          <input
            name="vq"
            type="number"
            step="1"
            required
            value={vq}
            onChange={(ev) => setVq(ev.target.value)}
          />
        </label>
        <label>
          F 月額固定・万円（利息・定額管理など）
          <input
            name="f"
            type="number"
            step="1"
            required
            value={f}
            onChange={(ev) => setF(ev.target.value)}
          />
        </label>
        <label>
          F 年額・万円（固都税・年払保険など → 月次では÷12・四捨五入）
          <input
            name="f_annual"
            type="number"
            step="1"
            value={fAnnual}
            onChange={(ev) => setFAnnual(ev.target.value)}
          />
        </label>
      </div>
      <div className="tax-form-row">
        <label>
          入金合計・万円
          <input name="cash_in" type="number" step="1" />
        </label>
        <label>
          出金合計・万円（元本返済含む可）
          <input name="cash_out" type="number" step="1" />
        </label>
        <label>
          期末現金・万円
          <input name="cash_end" type="number" step="1" />
        </label>
        <label>
          うち減価・万円（F内・参考）
          <input name="depreciation_jpy" type="number" step="1" />
        </label>
      </div>
      <label style={{ display: "block", marginTop: 8 }}>
        メモ
        <input name="note" type="text" style={{ width: "100%" }} />
      </label>
      <p className="meta" style={{ marginTop: 8 }}>
        プレビュー: MQ {fmtMqMan(preview.mq)} · G{" "}
        {fmtMqMan(preview.g)} · m/p {formatRatio(preview.mOverP)}
        {!preview.equationOk ? " · ⚠ 方程式不一致" : ""}
      </p>
      <p className="meta">
        合算表示用に入れる値は、個人↔法人の内部取引を除いたあとが望ましいです。
      </p>
      <button className="btn primary" type="submit" disabled={busy}>
        {busy ? "保存中…" : "実績を保存"}
      </button>
      {msg ? <p className="meta">{msg}</p> : null}
    </form>
  );
}
