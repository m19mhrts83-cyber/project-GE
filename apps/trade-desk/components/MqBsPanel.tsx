"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { fmtYen } from "@/lib/format";
import {
  BS_FIELD_LABELS,
  isBsBalanced,
  isBsComplete,
  missingBsFields,
  normalizeBs,
  resolveCurrentProfit,
  sumAssets,
  sumLiabEquity,
  type MqBsFields,
} from "@/lib/mqBs";
import { MQ_POLICY } from "@/lib/mqPolicy";

function yenOrNeed(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "要確認";
  return fmtYen(Math.round(n));
}

function fieldDefault(
  k: keyof MqBsFields,
  overrides: Partial<Record<keyof MqBsFields, string>>,
  initial: Partial<MqBsFields> | undefined,
  base: MqBsFields
): string {
  if (overrides[k] != null) return overrides[k]!;
  if (initial?.[k] != null) return String(initial[k]);
  if (base[k] != null) return String(base[k]);
  return "";
}

type Props = {
  title: string;
  fields: MqBsFields | null;
  mqG?: number | null;
  asOfLabel: string;
  combineNote?: string | null;
  requireInventory?: boolean;
  defaultLine: "realestate" | "ai";
  defaultEntity: "personal" | "corporate";
  defaultAsOf: string;
  initial?: Partial<MqBsFields> & { note?: string | null };
  loanTrackerLt?: number | null;
  priorYearCash?: number | null;
  priorYearAsOf?: string | null;
};

export default function MqBsPanel({
  title,
  fields,
  mqG,
  asOfLabel,
  combineNote,
  requireInventory = false,
  defaultLine,
  defaultEntity,
  defaultAsOf,
  initial,
  loanTrackerLt,
  priorYearCash,
  priorYearAsOf,
}: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [overrides, setOverrides] = useState<
    Partial<Record<keyof MqBsFields, string>>
  >({});

  const base = fields ?? normalizeBs(initial || {});
  const profit = resolveCurrentProfit(base, mqG);
  const display: MqBsFields = {
    ...base,
    current_profit: profit.value,
  };
  const complete = isBsComplete(base, { requireInventory });
  const balanced = isBsBalanced(
    { ...base, current_profit: base.current_profit ?? profit.value },
    { requireInventory }
  );
  const missing = missingBsFields(base, { requireInventory });

  const assets = sumAssets(display);
  const liabEq = sumLiabEquity({
    ...display,
    current_profit: profit.value,
  });

  const preview = useMemo(() => display, [display]);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    const fd = new FormData(e.currentTarget);
    const num = (k: string) => {
      const v = fd.get(k);
      if (v == null || String(v).trim() === "") return null;
      return v;
    };
    const body = {
      business_line: String(fd.get("business_line")),
      entity: String(fd.get("entity")),
      as_of_date: String(fd.get("as_of_date")),
      cash: num("cash"),
      receivables: num("receivables"),
      inventory: num("inventory"),
      fixed_assets: num("fixed_assets"),
      liabilities_st: num("liabilities_st"),
      liabilities_lt: num("liabilities_lt"),
      capital: num("capital"),
      retained_earnings: num("retained_earnings"),
      current_profit: num("current_profit"),
      note: fd.get("note") || null,
      source: "manual",
    };
    try {
      const res = await fetch("/api/mq/bs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        setMsg(String(json.error || `HTTP ${res.status}`));
        return;
      }
      setMsg("B/Sを保存しました");
      setOpen(false);
      setOverrides({});
      router.refresh();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "保存に失敗");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card mq-bs">
      <header>
        <span className="lvl">軽量B/S</span>
        <strong>{title}</strong>
      </header>
      <p className="meta" style={{ marginTop: 6 }}>
        基準日 {asOfLabel}
        {!complete
          ? " · 未入力あり（捏造しません）"
          : balanced
            ? " · 貸借一致"
            : " · 貸借不一致"}
      </p>
      <p className="meta" style={{ marginTop: 4 }}>
        {MQ_POLICY.cashNote}
      </p>
      {combineNote ? (
        <p className="meta" style={{ color: "var(--high)", marginTop: 4 }}>
          {combineNote}
        </p>
      ) : null}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 12,
          marginTop: 10,
        }}
      >
        <table>
          <thead>
            <tr>
              <th>資産</th>
              <th className="num">金額</th>
            </tr>
          </thead>
          <tbody>
            {(
              ["cash", "receivables", "inventory", "fixed_assets"] as const
            ).map((k) => (
              <tr key={k}>
                <td>
                  {k === "cash"
                    ? "現金・預金（家計含む・参考）"
                    : BS_FIELD_LABELS[k]}
                  {k === "inventory" && !requireInventory ? (
                    <span className="meta">（賃貸は任意）</span>
                  ) : null}
                </td>
                <td className="num">{yenOrNeed(preview[k])}</td>
              </tr>
            ))}
            <tr>
              <td>
                <strong>資産合計</strong>
              </td>
              <td className="num">
                <strong>
                  {complete || assets !== 0 ? yenOrNeed(assets) : "要確認"}
                </strong>
              </td>
            </tr>
          </tbody>
        </table>
        <table>
          <thead>
            <tr>
              <th>負債・資本</th>
              <th className="num">金額</th>
            </tr>
          </thead>
          <tbody>
            {(
              [
                "liabilities_st",
                "liabilities_lt",
                "capital",
                "retained_earnings",
                "current_profit",
              ] as const
            ).map((k) => (
              <tr key={k}>
                <td>
                  {BS_FIELD_LABELS[k]}
                  {k === "current_profit" && profit.fromMq ? (
                    <span className="meta">（MQのG・参考）</span>
                  ) : null}
                </td>
                <td className="num">
                  {k === "current_profit"
                    ? yenOrNeed(profit.value)
                    : yenOrNeed(preview[k])}
                </td>
              </tr>
            ))}
            <tr>
              <td>
                <strong>負債・資本合計</strong>
              </td>
              <td className="num">
                <strong>{yenOrNeed(liabEq)}</strong>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {missing.length > 0 ? (
        <p className="meta" style={{ marginTop: 8 }}>
          要確認: {missing.map((k) => BS_FIELD_LABELS[k]).join("、")}
        </p>
      ) : null}

      <div style={{ marginTop: 10, display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button type="button" className="btn" onClick={() => setOpen((v) => !v)}>
          {open ? "入力を閉じる" : "穴埋め入力"}
        </button>
        {loanTrackerLt != null ? (
          <button
            type="button"
            className="btn"
            onClick={() => {
              setOpen(true);
              setOverrides((o) => ({
                ...o,
                liabilities_lt: String(loanTrackerLt),
              }));
              setMsg(
                `長期他人資本にトラッカー残高 ${fmtYen(loanTrackerLt)} をセット（保存で確定）`
              );
            }}
          >
            ローン残高を反映（候補）
          </button>
        ) : null}
        {priorYearCash != null ? (
          <button
            type="button"
            className="btn"
            onClick={() => {
              setOpen(true);
              setOverrides((o) => ({
                ...o,
                cash: String(priorYearCash),
              }));
              setMsg(
                `前年繰越現金 ${fmtYen(priorYearCash)}${
                  priorYearAsOf ? `（${priorYearAsOf}）` : ""
                } をセット（保存で確定）`
              );
            }}
          >
            前年現金を繰越セット
          </button>
        ) : null}
      </div>

      {open ? (
        <form onSubmit={onSubmit} style={{ marginTop: 12 }}>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
              gap: 8,
            }}
          >
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
              基準日（年次クローズは12/31推奨）
              <input
                name="as_of_date"
                type="date"
                defaultValue={defaultAsOf}
                required
              />
            </label>
            {(Object.keys(BS_FIELD_LABELS) as (keyof MqBsFields)[]).map(
              (k) => (
                <label key={k}>
                  {k === "cash"
                    ? "現金・預金（家計含む）"
                    : BS_FIELD_LABELS[k]}
                  <input
                    name={k}
                    type="number"
                    step="1"
                    key={`${k}-${overrides[k] ?? ""}`}
                    defaultValue={fieldDefault(k, overrides, initial, base)}
                    placeholder="空=要確認"
                  />
                </label>
              )
            )}
            <label style={{ gridColumn: "1 / -1" }}>
              メモ（税理士試算表からの補正など）
              <input name="note" defaultValue={initial?.note || ""} />
            </label>
          </div>
          <p className="meta" style={{ marginTop: 6 }}>
            空欄は NULL のまま。ローンはトラッカー候補→手入力で補正。年別クローズ後は翌年に繰越セット。
          </p>
          <button
            type="submit"
            className="btn primary"
            disabled={busy}
            style={{ marginTop: 8 }}
          >
            {busy ? "保存中…" : "B/Sを保存"}
          </button>
          {msg ? (
            <p className="meta" style={{ marginTop: 6 }}>
              {msg}
            </p>
          ) : null}
        </form>
      ) : msg ? (
        <p className="meta" style={{ marginTop: 6 }}>
          {msg}
        </p>
      ) : null}
    </div>
  );
}
