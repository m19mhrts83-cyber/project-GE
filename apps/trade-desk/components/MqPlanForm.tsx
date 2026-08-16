"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { computeMq, formatRatio } from "@/lib/mqEquations";
import { fmtMqMan } from "@/lib/mqUnits";
import { qFieldLabel } from "@/lib/mqPolicy";

type Props = {
  defaultLine: "realestate" | "ai";
  defaultEntity: "personal" | "corporate";
  defaultYear: string;
  existingVariants: string[];
};

export default function MqPlanForm({
  defaultLine,
  defaultEntity,
  defaultYear,
  existingVariants,
}: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [pq, setPq] = useState("");
  const [vq, setVq] = useState("");
  const [f, setF] = useState("");
  const [q, setQ] = useState("");
  const [variant, setVariant] = useState(existingVariants[0] || "基本");

  const preview = useMemo(
    () =>
      computeMq({
        pq: Number(pq) || 0,
        vq: Number(vq) || 0,
        f: Number(f) || 0,
        q: q === "" ? null : Number(q),
      }),
    [pq, vq, f, q]
  );
  const monthly = useMemo(
    () =>
      computeMq({
        pq: preview.pq / 12,
        vq: preview.vq / 12,
        f: preview.f / 12,
        q: preview.q != null ? preview.q / 12 : null,
      }),
    [preview]
  );

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    const fd = new FormData(e.currentTarget);
    const year = String(fd.get("plan_year") || defaultYear).slice(0, 4);
    const plan_variant_id = String(fd.get("plan_variant_id") || "").trim();
    if (!plan_variant_id) {
      setMsg("計画名を入力してください");
      setBusy(false);
      return;
    }
    const body = {
      business_line: String(fd.get("business_line")),
      entity: String(fd.get("entity")),
      period_month: `${year}-01`,
      scenario_kind: "plan",
      plan_variant_id,
      q: fd.get("q") === "" ? null : fd.get("q"),
      pq: fd.get("pq"),
      vq: fd.get("vq"),
      f: fd.get("f"),
      f_annual: 0,
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
      setMsg("計画を保存しました");
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
          計画名（パターン）
          <input
            name="plan_variant_id"
            list="mq-plan-variants"
            value={variant}
            onChange={(ev) => setVariant(ev.target.value)}
            placeholder="例: 基本 / 家賃+5% / 空室改善"
            required
          />
          <datalist id="mq-plan-variants">
            {existingVariants.map((v) => (
              <option key={v} value={v} />
            ))}
          </datalist>
        </label>
        <label>
          年度（暦年）
          <input
            name="plan_year"
            type="number"
            min={2000}
            max={2100}
            defaultValue={defaultYear}
            required
          />
        </label>
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
      </div>
      <div className="tax-form-row">
        <label>
          {qFieldLabel(defaultLine)}（年合計）
          <input
            name="q"
            type="number"
            step="any"
            value={q}
            onChange={(ev) => setQ(ev.target.value)}
            placeholder={
              defaultLine === "ai" ? "例: 年間案件数" : "例: 稼働戸×12"
            }
          />
        </label>
        <label>
          PQ 年額・万円
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
          VQ 年額・万円
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
          F 年額・万円（利息・固都税など全部）
          <input
            name="f"
            type="number"
            step="1"
            required
            value={f}
            onChange={(ev) => setF(ev.target.value)}
          />
        </label>
      </div>
      <label style={{ display: "block", marginTop: 8 }}>
        メモ
        <input name="note" type="text" style={{ width: "100%" }} />
      </label>
      <p className="meta" style={{ marginTop: 8 }}>
        年次プレビュー: MQ {fmtMqMan(preview.mq)} · G{" "}
        {fmtMqMan(preview.g)} · m/p {formatRatio(preview.mOverP)}
      </p>
      <p className="meta">
        月次換算（÷12・四捨五入）: MQ {fmtMqMan(monthly.mq)} · G{" "}
        {fmtMqMan(monthly.g)}（実績月次と比較用）
      </p>
      <button className="btn primary" type="submit" disabled={busy}>
        {busy ? "保存中…" : "年次計画を保存"}
      </button>
      {msg ? <p className="meta">{msg}</p> : null}
    </form>
  );
}
