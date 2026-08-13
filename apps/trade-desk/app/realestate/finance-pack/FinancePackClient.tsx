"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  BANK_PROFILES,
  OWNERSHIP_LABELS,
  PRODUCT_TYPE_LABELS,
  buildEmailDraft,
  buildShortageText,
  filterFinanceSlots,
  type Ownership,
  type ProductType,
} from "@/lib/financePackCatalog";

const STORAGE_KEY = "kurashift_finance_pack_v1";

type CaseState = {
  productType: ProductType;
  ownership: "personal" | "corporate";
  bankId: string;
  caseName: string;
  amountNote: string;
  status: Record<string, string>;
  pathNotes: Record<string, string>;
};

const STATUS_OPTS = [
  { v: "todo", l: "未着手" },
  { v: "have", l: "取得済" },
  { v: "need_original", l: "要原本" },
  { v: "sent", l: "送信済" },
] as const;

function defaultCase(): CaseState {
  return {
    productType: "property_purchase",
    ownership: "personal",
    bankId: "shiga",
    caseName: "",
    amountNote: "",
    status: {},
    pathNotes: {},
  };
}

export default function FinancePackClient({
  loanSummary,
}: {
  loanSummary: string;
}) {
  const [state, setState] = useState<CaseState>(defaultCase);
  const [copied, setCopied] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) setState({ ...defaultCase(), ...JSON.parse(raw) });
    } catch {
      /* ignore */
    }
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }, [state, hydrated]);

  const slots = useMemo(
    () =>
      filterFinanceSlots({
        productType: state.productType,
        ownership: state.ownership,
        bankId: state.bankId,
      }),
    [state.productType, state.ownership, state.bankId]
  );

  const bank = BANK_PROFILES.find((b) => b.id === state.bankId);
  const meta = {
    productLabel: PRODUCT_TYPE_LABELS[state.productType],
    ownershipLabel: OWNERSHIP_LABELS[state.ownership],
    bankLabel: bank?.label || state.bankId,
  };

  const shortage = buildShortageText(slots, state.status, meta);
  const email = buildEmailDraft({
    ...meta,
    amountNote: state.amountNote || undefined,
    shortageText: shortage,
  });

  const copy = useCallback(async (label: string, text: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(label);
    setTimeout(() => setCopied(null), 2000);
  }, []);

  const banksForProduct = BANK_PROFILES.filter((b) =>
    b.product_types.includes(state.productType)
  );

  return (
    <>
      <div className="card">
        <header>
          <span className="lvl">案件</span>
          <strong>商品・名義・先方</strong>
        </header>
        <div
          style={{
            display: "grid",
            gap: 12,
            marginTop: 12,
            gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))",
          }}
        >
          <label className="meta">
            商品タイプ
            <select
              value={state.productType}
              onChange={(e) => {
                const productType = e.target.value as ProductType;
                const nextBanks = BANK_PROFILES.filter((b) =>
                  b.product_types.includes(productType)
                );
                setState((s) => ({
                  ...s,
                  productType,
                  bankId: nextBanks.some((b) => b.id === s.bankId)
                    ? s.bankId
                    : nextBanks[0]?.id || s.bankId,
                }));
              }}
              style={{ display: "block", width: "100%", marginTop: 4 }}
            >
              {(Object.keys(PRODUCT_TYPE_LABELS) as ProductType[]).map((k) => (
                <option key={k} value={k}>
                  {PRODUCT_TYPE_LABELS[k]}
                </option>
              ))}
            </select>
          </label>
          <label className="meta">
            名義
            <select
              value={state.ownership}
              onChange={(e) =>
                setState((s) => ({
                  ...s,
                  ownership: e.target.value as "personal" | "corporate",
                }))
              }
              style={{ display: "block", width: "100%", marginTop: 4 }}
            >
              <option value="personal">個人</option>
              <option value="corporate">法人</option>
            </select>
          </label>
          <label className="meta">
            銀行／制度
            <select
              value={state.bankId}
              onChange={(e) =>
                setState((s) => ({ ...s, bankId: e.target.value }))
              }
              style={{ display: "block", width: "100%", marginTop: 4 }}
            >
              {banksForProduct.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.label}
                </option>
              ))}
            </select>
          </label>
          <label className="meta">
            案件メモ名
            <input
              value={state.caseName}
              onChange={(e) =>
                setState((s) => ({ ...s, caseName: e.target.value }))
              }
              placeholder="例: 202608_caramel_marukei"
              style={{ display: "block", width: "100%", marginTop: 4 }}
            />
          </label>
          <label className="meta" style={{ gridColumn: "1 / -1" }}>
            希望額メモ
            <input
              value={state.amountNote}
              onChange={(e) =>
                setState((s) => ({ ...s, amountNote: e.target.value }))
              }
              placeholder="例: 運転資金 500万円目安"
              style={{ display: "block", width: "100%", marginTop: 4 }}
            />
          </label>
        </div>
        {bank?.note ? (
          <p className="meta" style={{ marginTop: 8 }}>
            {bank.note}
          </p>
        ) : null}
        <p
          className="meta"
          style={{
            marginTop: 8,
            padding: "8px 10px",
            background: "var(--warn-bg, #fff8e1)",
            borderRadius: 6,
          }}
        >
          <strong>端末依存:</strong> チェック状態はこのブラウザの localStorage
          のみ（別端末・別ブラウザには引き継がれません）。正本ファイルは OneDrive{" "}
          <code>
            240_融資/finance_packs/&#123;YYYYMM&#125;_&#123;略称&#125;/
          </code>
          。自動送信はしません。
        </p>
      </div>

      <div className="card notice">
        <header>
          <span className="lvl">共通</span>
          <strong>マイナンバーカードは常に先頭ブロック</strong>
        </header>
        <p className="meta" style={{ marginTop: 8 }}>
          個人／法人を切り替えても共通スロット（マイナ・免許・保険証・既存借入）は残ります。
          正本 YAML: <code>config/kurashift_re_finance_doc_templates.yaml</code>
        </p>
        <p className="meta" style={{ marginTop: 4 }}>
          既存借入（投影）: {loanSummary}
        </p>
      </div>

      <div className="card">
        <header>
          <span className="lvl">Checklist</span>
          <strong>
            {meta.productLabel} · {meta.ownershipLabel} · {meta.bankLabel}
          </strong>
        </header>
        <table>
          <thead>
            <tr>
              <th>区分</th>
              <th>項目</th>
              <th>状態</th>
              <th>パス／メモ</th>
              <th>取り方</th>
            </tr>
          </thead>
          <tbody>
            {slots.map((s) => (
              <tr key={s.id}>
                <td className="meta">
                  {OWNERSHIP_LABELS[s.ownership as Ownership]}
                  {s.layer === "deal" ? "・案件" : ""}
                </td>
                <td>
                  {s.title}
                  {s.media === "mail_original" ? (
                    <span className="meta"> ·原本</span>
                  ) : null}
                </td>
                <td>
                  <select
                    value={state.status[s.id] || "todo"}
                    onChange={(e) =>
                      setState((st) => ({
                        ...st,
                        status: { ...st.status, [s.id]: e.target.value },
                      }))
                    }
                  >
                    {STATUS_OPTS.map((o) => (
                      <option key={o.v} value={o.v}>
                        {o.l}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  <input
                    value={state.pathNotes[s.id] || ""}
                    placeholder={s.path_hint || ""}
                    onChange={(e) =>
                      setState((st) => ({
                        ...st,
                        pathNotes: {
                          ...st.pathNotes,
                          [s.id]: e.target.value,
                        },
                      }))
                    }
                    style={{ width: "100%", minWidth: 120 }}
                  />
                </td>
                <td className="meta">{s.how || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <header>
          <span className="lvl">Actions</span>
          <strong>不足一覧・メール下書き</strong>
        </header>
        <p className="meta" style={{ marginTop: 8 }}>
          送信はしません。コピー後、確認してから送ってください（outbound-confirm）。
        </p>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
          <button type="button" onClick={() => copy("shortage", shortage)}>
            不足一覧をコピー
          </button>
          <button type="button" onClick={() => copy("email", email)}>
            メール下書きをコピー
          </button>
          {copied ? (
            <span className="meta">コピーしました（{copied}）</span>
          ) : null}
        </div>
        <pre
          className="meta"
          style={{
            marginTop: 12,
            whiteSpace: "pre-wrap",
            fontSize: 12,
            maxHeight: 280,
            overflow: "auto",
          }}
        >
          {email}
        </pre>
      </div>
    </>
  );
}
