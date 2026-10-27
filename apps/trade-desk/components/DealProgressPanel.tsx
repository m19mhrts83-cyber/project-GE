"use client";

import { useEffect, useState } from "react";
import {
  ACQ_STAGES,
  VIEWING_CHECKLIST,
  VIEWING_STEP_LABEL,
  acqStageDef,
  acqStageIndex,
  acquisitionNextStep,
  checklistProgress,
  getAcquisition,
  getViewing,
  grokRequestText,
  viewingNextStep,
  type AcqStage,
  type ProgressBody,
  type ViewingStep,
} from "@/lib/reDealStages";
import { TARGET_YIELD, deskGate } from "@/lib/reViewingGate";

type Deal = {
  id: string;
  title: string;
  status: string;
  area?: string | null;
  price_man?: number | null;
  summary_json?: Record<string, unknown>;
};

const box: React.CSSProperties = {
  marginTop: 12,
  padding: 12,
  borderRadius: 8,
};
const smallBtn: React.CSSProperties = { fontSize: 12, padding: "4px 8px" };
const input: React.CSSProperties = {
  fontSize: 13,
  padding: "4px 6px",
  border: "1px solid #cbd5e1",
  borderRadius: 4,
  maxWidth: "100%",
};

function NextLine({ label, urgent }: { label: string; urgent: boolean }) {
  return (
    <div
      style={{
        fontSize: 12,
        fontWeight: 600,
        padding: "6px 8px",
        borderRadius: 4,
        background: urgent ? "#fef3c7" : "#f1f5f9",
        color: urgent ? "#92400e" : "#334155",
        margin: "8px 0",
      }}
    >
      ▶ 次にやること: {label}
    </div>
  );
}

export default function DealProgressPanel({
  deal,
  onChanged,
}: {
  deal: Deal;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const sj = deal.summary_json || {};
  const viewing = getViewing(deal);
  const acq = getAcquisition(deal);
  const st = deal.status;
  const inAcquisition = st === "offer" || st === "loan" || st === "purchased";

  const [memo, setMemo] = useState(viewing.memo || "");
  const [acqMemo, setAcqMemo] = useState(acq.memo || "");
  useEffect(() => setMemo(viewing.memo || ""), [viewing.memo]);
  useEffect(() => setAcqMemo(acq.memo || ""), [acq.memo]);

  const s3 =
    sj.s3_investigation && typeof sj.s3_investigation === "object"
      ? (sj.s3_investigation as { hearing_questions?: string[]; viewing_checks?: string[] })
      : null;
  const questions = s3?.hearing_questions || [];
  const viewingChecks = s3?.viewing_checks || [];

  async function save(body: ProgressBody, okMsg = "保存しました") {
    setBusy(true);
    setMsg(null);
    try {
      const res = await fetch(`/api/re/deals/${deal.id}/progress`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setMsg(data.error || "保存に失敗しました");
      } else {
        setMsg(okMsg);
        onChanged();
      }
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "エラー");
    } finally {
      setBusy(false);
    }
  }

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setMsg("Grok への依頼文をコピーしました（貼り付けて送るのは自分で）");
    } catch {
      setMsg("コピーできませんでした");
    }
  }

  if (st === "archived") return null;

  if (!inAcquisition) {
    if (st === "passed" && !viewing.step) return null;
    const step: ViewingStep = viewing.step || "candidate";
    const next = viewingNextStep(deal);
    const prog = checklistProgress(VIEWING_CHECKLIST, viewing.checklist);
    const gate = deskGate(deal);
    const rentSourceLabel =
      gate.rentSource === "manual" ? "手入力" : gate.rentSource ? "S3" : "未設定";
    return (
      <div style={{ ...box, border: "2px solid #0ea5e9", background: "#f0f9ff" }}>
        <strong>🚶 内見（{VIEWING_STEP_LABEL[step]}）</strong>
        <NextLine {...next} />

        <div
          style={{
            fontSize: 12,
            background: "#fff",
            border: `1px solid ${gate.verdict === "go" ? "#16a34a" : "#bae6fd"}`,
            borderRadius: 6,
            padding: "8px 10px",
            marginBottom: 8,
          }}
        >
          <div style={{ fontWeight: 600 }}>
            机上判定（内見に行くか）: {gate.label}
          </div>
          <div className="meta" style={{ marginTop: 2 }}>
            指値ライン＝保守の想定家賃×12÷{Math.round(TARGET_YIELD * 100)}%−修繕概算。家賃の出どころ:{" "}
            {rentSourceLabel}
            {gate.rentMan != null ? `（${gate.rentMan}万円/月）` : ""}
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 6 }}>
            <label className="meta">
              保守の想定家賃（万円/月）{" "}
              <input
                type="number"
                step="0.1"
                style={{ ...input, width: 80 }}
                defaultValue={viewing.desk_rent_man ?? ""}
                key={`dr-${viewing.desk_rent_man ?? ""}`}
                placeholder={gate.rentSource && gate.rentSource !== "manual" ? String(gate.rentMan) : ""}
                onBlur={(e) => {
                  const v = e.target.value === "" ? null : Number(e.target.value);
                  if (v !== (viewing.desk_rent_man ?? null)) {
                    void save({ kind: "viewing", patch: { desk_rent_man: v } });
                  }
                }}
              />
            </label>
            <label className="meta">
              修繕概算（万円）{" "}
              <input
                type="number"
                style={{ ...input, width: 80 }}
                defaultValue={viewing.repair_man ?? ""}
                key={`rp-${viewing.repair_man ?? ""}`}
                placeholder="内見後"
                onBlur={(e) => {
                  const v = e.target.value === "" ? null : Number(e.target.value);
                  if (v !== (viewing.repair_man ?? null)) {
                    void save({ kind: "viewing", patch: { repair_man: v } });
                  }
                }}
              />
            </label>
          </div>
          {viewingChecks.length > 0 ? (
            <div style={{ marginTop: 6 }}>
              <div style={{ fontWeight: 600 }}>内見で確かめること（S3）</div>
              <ol style={{ margin: "2px 0 0 18px", padding: 0 }}>
                {viewingChecks.map((q, i) => (
                  <li key={i}>{q}</li>
                ))}
              </ol>
            </div>
          ) : null}
        </div>

        <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
          {(Object.keys(VIEWING_STEP_LABEL) as ViewingStep[]).map((s) => (
            <button
              key={s}
              type="button"
              className="btn"
              disabled={busy}
              onClick={() => save({ kind: "viewing", patch: { step: s } })}
              style={{
                ...smallBtn,
                background: s === step ? "#0369a1" : undefined,
                color: s === step ? "#fff" : undefined,
              }}
            >
              {VIEWING_STEP_LABEL[s]}
            </button>
          ))}
        </div>

        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8, alignItems: "center" }}>
          <label className="meta">
            内見日{" "}
            <input
              type="date"
              style={input}
              defaultValue={viewing.date || ""}
              key={`d-${viewing.date || ""}`}
              disabled={busy}
              onChange={(e) =>
                save({ kind: "viewing", patch: { date: e.target.value || null } }, "内見日を保存しました")
              }
            />
          </label>
          <label className="meta">
            時刻{" "}
            <input
              type="time"
              style={input}
              defaultValue={viewing.time || ""}
              key={`t-${viewing.time || ""}`}
              disabled={busy}
              onBlur={(e) => {
                if ((e.target.value || null) !== (viewing.time || null)) {
                  void save({ kind: "viewing", patch: { time: e.target.value || null } });
                }
              }}
            />
          </label>
        </div>
        <label className="meta" style={{ display: "block", marginTop: 6 }}>
          仲介・担当{" "}
          <input
            type="text"
            style={{ ...input, width: 240 }}
            defaultValue={viewing.contact || ""}
            key={`c-${viewing.contact || ""}`}
            placeholder="例: ○○不動産 山田さん"
            onBlur={(e) => {
              if (e.target.value !== (viewing.contact || "")) {
                void save({ kind: "viewing", patch: { contact: e.target.value } });
              }
            }}
          />
        </label>

        <div style={{ marginTop: 10, fontSize: 12 }}>
          <div style={{ fontWeight: 600 }}>
            内見チェック（{prog.done}/{prog.total}）
          </div>
          {VIEWING_CHECKLIST.map((it) => (
            <label key={it.key} style={{ display: "block", marginTop: 3 }}>
              <input
                type="checkbox"
                checked={Boolean(viewing.checklist?.[it.key])}
                disabled={busy}
                onChange={(e) =>
                  save({ kind: "viewing", patch: { checklist: { [it.key]: e.target.checked } } })
                }
              />{" "}
              {it.label}
              {it.hint ? <span className="meta">（{it.hint}）</span> : null}
            </label>
          ))}
        </div>

        {questions.length > 0 ? (
          <div style={{ marginTop: 10, fontSize: 12 }}>
            <div style={{ fontWeight: 600 }}>
              ヒアリング回答（S3 項目 · 聞いたら記入）
            </div>
            {questions.map((q, i) => (
              <div key={i} style={{ marginTop: 6 }}>
                <div>
                  {i + 1}. {q}
                </div>
                <textarea
                  rows={2}
                  style={{ ...input, width: "100%" }}
                  defaultValue={viewing.hearing_answers?.[String(i)] || ""}
                  placeholder="回答・確認結果"
                  onBlur={(e) => {
                    if (e.target.value !== (viewing.hearing_answers?.[String(i)] || "")) {
                      void save({
                        kind: "viewing",
                        patch: { hearing_answers: { [String(i)]: e.target.value } },
                      });
                    }
                  }}
                />
              </div>
            ))}
          </div>
        ) : null}

        <div style={{ marginTop: 10 }}>
          <div style={{ fontSize: 12, fontWeight: 600 }}>内見メモ</div>
          <textarea
            rows={3}
            style={{ ...input, width: "100%" }}
            value={memo}
            onChange={(e) => setMemo(e.target.value)}
            placeholder="建物の状態・周辺・仲介の話・気になった点"
          />
          <button
            type="button"
            className="btn"
            style={smallBtn}
            disabled={busy || memo === (viewing.memo || "")}
            onClick={() => save({ kind: "viewing", patch: { memo } })}
          >
            メモを保存
          </button>
          <button
            type="button"
            className="btn"
            style={{ ...smallBtn, marginLeft: 4 }}
            onClick={() => copy(grokRequestText("viewing", deal))}
          >
            S7 融資の当たり依頼文をコピー
          </button>
        </div>

        <div style={{ marginTop: 12, borderTop: "1px solid #bae6fd", paddingTop: 8 }}>
          <div style={{ fontSize: 12, fontWeight: 600 }}>内見の結果</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 4 }}>
            <button
              type="button"
              className="btn"
              disabled={busy}
              style={{ ...smallBtn, background: "#16a34a", color: "#fff" }}
              onClick={() => {
                if (window.confirm("買付準備へ進めます（status=買付）。よろしいですか？")) {
                  void save({ kind: "start_acquisition" }, "買付準備に進めました");
                }
              }}
            >
              買付へ進む
            </button>
            <button
              type="button"
              className="btn"
              disabled={busy}
              style={smallBtn}
              onClick={() => save({ kind: "viewing", patch: { step: "done", verdict: "hold" } })}
            >
              保留
            </button>
            <button
              type="button"
              className="btn"
              disabled={busy}
              style={smallBtn}
              onClick={() => {
                if (window.confirm("見送りにします。よろしいですか？")) {
                  void save({ kind: "viewing", patch: { step: "done", verdict: "pass" } });
                }
              }}
            >
              見送り
            </button>
          </div>
          {viewing.verdict === "hold" ? (
            <p className="meta" style={{ marginTop: 4 }}>
              保留中。条件が変われば「買付へ進む」を押してください。
            </p>
          ) : null}
        </div>
        {msg ? <div className="meta" style={{ marginTop: 6 }}>{msg}</div> : null}
      </div>
    );
  }

  const stage = (acq.stage || "offer_prep") as AcqStage;
  const def = acqStageDef(stage)!;
  const idx = acqStageIndex(stage);
  const next = acquisitionNextStep(deal);
  const nextDef = ACQ_STAGES[idx + 1];
  return (
    <div style={{ ...box, border: "2px solid #16a34a", background: "#f0fdf4" }}>
      <strong>🧾 買付〜引渡し（{def.label}）</strong>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 2, marginTop: 8 }}>
        {ACQ_STAGES.map((s, i) => (
          <button
            key={s.key}
            type="button"
            disabled={busy}
            title={`${s.label} · 担当: ${s.owner}`}
            onClick={() => {
              if (s.key === stage) return;
              if (window.confirm(`段階を「${s.label}」にします。よろしいですか？`)) {
                void save({ kind: "acquisition", patch: { stage: s.key } });
              }
            }}
            style={{
              fontSize: 11,
              padding: "3px 6px",
              borderRadius: 4,
              border: "1px solid #86efac",
              cursor: "pointer",
              background: i < idx ? "#bbf7d0" : i === idx ? "#15803d" : "#fff",
              color: i === idx ? "#fff" : "#166534",
              fontWeight: i === idx ? 700 : 400,
            }}
          >
            {i < idx ? "✓ " : ""}
            {s.label}
          </button>
        ))}
      </div>
      <NextLine label={next.label} urgent={next.urgent} />
      <div className="meta">担当: {def.owner}</div>

      <label className="meta" style={{ display: "block", marginTop: 6 }}>
        {def.dateLabel}{" "}
        <input
          type="date"
          style={input}
          defaultValue={acq.dates?.[stage] || ""}
          key={`ad-${stage}-${acq.dates?.[stage] || ""}`}
          disabled={busy}
          onChange={(e) =>
            save({ kind: "acquisition", patch: { dates: { [stage]: e.target.value } } })
          }
        />
      </label>

      <div style={{ marginTop: 8, fontSize: 12 }}>
        {def.checklist.map((it) => (
          <label key={it.key} style={{ display: "block", marginTop: 3 }}>
            <input
              type="checkbox"
              checked={Boolean(acq.checklist?.[`${stage}.${it.key}`])}
              disabled={busy}
              onChange={(e) =>
                save({
                  kind: "acquisition",
                  patch: { checklist: { [`${stage}.${it.key}`]: e.target.checked } },
                })
              }
            />{" "}
            {it.label}
          </label>
        ))}
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 8 }}>
        <button
          type="button"
          className="btn"
          style={smallBtn}
          onClick={() =>
            copy(
              grokRequestText(stage, deal, { memo: viewing.memo })
            )
          }
        >
          Grok 依頼文をコピー
        </button>
        {nextDef ? (
          <button
            type="button"
            className="btn"
            disabled={busy}
            style={{ ...smallBtn, background: "#16a34a", color: "#fff" }}
            onClick={() => {
              if (window.confirm(`「${nextDef.label}」へ進めます。よろしいですか？`)) {
                void save({ kind: "acquisition", patch: { stage: nextDef.key } });
              }
            }}
          >
            {nextDef.label}へ進める →
          </button>
        ) : null}
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 10 }}>
        <label className="meta">
          買付価格（万円）{" "}
          <input
            type="number"
            style={{ ...input, width: 90 }}
            defaultValue={acq.offer_price_man ?? ""}
            key={`op-${acq.offer_price_man ?? ""}`}
            onBlur={(e) => {
              const v = e.target.value === "" ? null : Number(e.target.value);
              if (v !== (acq.offer_price_man ?? null)) {
                void save({ kind: "acquisition", patch: { offer_price_man: v } });
              }
            }}
          />
        </label>
        <label className="meta">
          融資額（万円）{" "}
          <input
            type="number"
            style={{ ...input, width: 90 }}
            defaultValue={acq.loan_amount_man ?? ""}
            key={`la-${acq.loan_amount_man ?? ""}`}
            onBlur={(e) => {
              const v = e.target.value === "" ? null : Number(e.target.value);
              if (v !== (acq.loan_amount_man ?? null)) {
                void save({ kind: "acquisition", patch: { loan_amount_man: v } });
              }
            }}
          />
        </label>
        <label className="meta">
          金融機関{" "}
          <input
            type="text"
            style={{ ...input, width: 140 }}
            defaultValue={acq.lender || ""}
            key={`ln-${acq.lender || ""}`}
            onBlur={(e) => {
              if (e.target.value !== (acq.lender || "")) {
                void save({ kind: "acquisition", patch: { lender: e.target.value } });
              }
            }}
          />
        </label>
      </div>

      {ACQ_STAGES.some((s) => acq.dates?.[s.key]) ? (
        <div className="meta" style={{ marginTop: 8 }}>
          日程:{" "}
          {ACQ_STAGES.filter((s) => acq.dates?.[s.key])
            .map((s) => `${s.label} ${acq.dates?.[s.key]}`)
            .join(" · ")}
        </div>
      ) : null}

      <div style={{ marginTop: 10 }}>
        <div style={{ fontSize: 12, fontWeight: 600 }}>メモ（交渉・融資条件・契約の論点）</div>
        <textarea
          rows={3}
          style={{ ...input, width: "100%" }}
          value={acqMemo}
          onChange={(e) => setAcqMemo(e.target.value)}
        />
        <button
          type="button"
          className="btn"
          style={smallBtn}
          disabled={busy || acqMemo === (acq.memo || "")}
          onClick={() => save({ kind: "acquisition", patch: { memo: acqMemo } })}
        >
          メモを保存
        </button>
      </div>
      {msg ? <div className="meta" style={{ marginTop: 6 }}>{msg}</div> : null}
    </div>
  );
}
