"use client";

import { useEffect, useMemo, useState } from "react";
import {
  appendPropertyUnitMemo,
  updatePropertyUnitTerms,
} from "@/app/actions/propertyUnitMemo";
import {
  FLOOR_MAP_LAYOUTS,
  fmtDiscount,
  fmtYen,
  shortLabel,
  unitRentBreakdown,
  unitRentPlan,
  type OccupancyEvent,
  type PropertyUnit,
} from "@/lib/occupancy";

type ManagerMap = Record<string, string | null>;

function hoverTitle(unit: PropertyUnit): string {
  const plan = unitRentPlan(unit);
  const bits = [
    unit.note || "",
    plan.plan_note || "",
    plan.campaign_until ? `キャンペーン期限: ${plan.campaign_until}` : "",
  ].filter(Boolean);
  return bits.join("\n") || "メモなし";
}

function fmtWhen(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 16);
  return d.toLocaleString("ja-JP", {
    timeZone: "Asia/Tokyo",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function numInput(v: number | null | undefined): string {
  return v == null ? "" : String(Math.round(v));
}

export default function UnitFloorMap({
  propertyId,
  propertyName,
  units,
  events,
  managers,
}: {
  propertyId: string;
  propertyName: string;
  units: PropertyUnit[];
  events: OccupancyEvent[];
  managers: ManagerMap;
}) {
  const layout = FLOOR_MAP_LAYOUTS[propertyId];
  const byRoom = useMemo(() => {
    const m = new Map<string, PropertyUnit>();
    for (const u of units) m.set(u.room, u);
    return m;
  }, [units]);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [memoText, setMemoText] = useState("");
  const [pending, setPending] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);
  const [localUnits, setLocalUnits] = useState(units);
  const [editOpen, setEditOpen] = useState(false);

  const [formRent, setFormRent] = useState("");
  const [formMgmt, setFormMgmt] = useState("");
  const [formY1, setFormY1] = useState("");
  const [formY2, setFormY2] = useState("");
  const [formUntil, setFormUntil] = useState("");
  const [formStatus, setFormStatus] = useState<"occupied" | "vacant">(
    "occupied",
  );
  const [formReason, setFormReason] = useState("");

  useEffect(() => {
    setLocalUnits(units);
  }, [units]);

  const localByRoom = useMemo(() => {
    const m = new Map<string, PropertyUnit>();
    for (const u of localUnits) m.set(u.room, u);
    return m;
  }, [localUnits]);

  const selected =
    (selectedId && localUnits.find((u) => u.id === selectedId)) || null;
  const selectedPlan = selected ? unitRentPlan(selected) : null;
  const selectedCurrent = selected ? unitRentBreakdown(selected) : null;
  const selectedEvents = selected
    ? events.filter(
        (e) =>
          e.property_id === selected.property_id && e.room === selected.room,
      )
    : [];

  useEffect(() => {
    if (!selected) return;
    const plan = unitRentPlan(selected);
    const cur = unitRentBreakdown(selected);
    setFormRent(numInput(cur.rent));
    setFormMgmt(numInput(cur.management_fee ?? plan.management_fee));
    setFormY1(numInput(plan.rent_year1));
    setFormY2(numInput(plan.rent_year2));
    setFormUntil(plan.campaign_until || "");
    setFormStatus(selected.status === "vacant" ? "vacant" : "occupied");
    setFormReason("");
    setEditOpen(false);
    setOkMsg(null);
  }, [selectedId]); // eslint-disable-line react-hooks/exhaustive-deps -- hydrate form when号室切替

  if (!layout) return null;

  async function onAppendMemo() {
    if (!selected) return;
    setPending(true);
    setErr(null);
    setOkMsg(null);
    const res = await appendPropertyUnitMemo({
      unitId: selected.id,
      text: memoText,
      source: "ui",
    });
    setPending(false);
    if (!res.ok) {
      setErr(res.error);
      return;
    }
    const at = new Date().toISOString();
    setLocalUnits((prev) =>
      prev.map((u) => {
        if (u.id !== selected.id) return u;
        const plan = unitRentPlan(u);
        return {
          ...u,
          note: res.note,
          payload: {
            ...(u.payload || {}),
            memo_log: [
              ...plan.memo_log,
              { at, text: memoText.trim().slice(0, 400), source: "ui" },
            ],
          },
        };
      }),
    );
    setMemoText("");
    setOkMsg("メモを追記しました");
  }

  async function onSaveTerms() {
    if (!selected) return;
    setPending(true);
    setErr(null);
    setOkMsg(null);
    const res = await updatePropertyUnitTerms({
      unitId: selected.id,
      rent: formRent,
      management_fee: formMgmt,
      rent_year1: formY1,
      rent_year2: formY2,
      campaign_until: formUntil,
      status: formStatus,
      reason: formReason,
      source: "ui",
    });
    setPending(false);
    if (!res.ok) {
      setErr(res.error);
      return;
    }
    setLocalUnits((prev) =>
      prev.map((u) =>
        u.id === selected.id
          ? {
              ...u,
              rent: res.unit.rent,
              status: res.unit.status,
              note: res.unit.note,
              payload: res.unit.payload,
            }
          : u,
      ),
    );
    const saved: PropertyUnit = {
      ...selected,
      rent: res.unit.rent,
      status: res.unit.status,
      note: res.unit.note,
      payload: res.unit.payload,
    };
    const plan = unitRentPlan(saved);
    const cur = unitRentBreakdown(saved);
    setFormRent(numInput(cur.rent));
    setFormMgmt(numInput(cur.management_fee ?? plan.management_fee));
    setFormY1(numInput(plan.rent_year1));
    setFormY2(numInput(plan.rent_year2));
    setFormUntil(plan.campaign_until || "");
    setFormStatus(saved.status === "vacant" ? "vacant" : "occupied");
    setFormReason("");
    setEditOpen(false);
    setOkMsg("条件を修正しました");
  }

  return (
    <div className="rent-map">
      <div
        className="rent-map-floors"
        role="group"
        aria-label={`${propertyName} 家賃マップ`}
      >
        {layout.floors.map((fl) => (
          <div key={fl.floor} className="rent-map-floor">
            <div className="rent-map-floor-label">{fl.floor}F</div>
            <div className="rent-map-row">
              {fl.rooms.map((room) => {
                const unit = localByRoom.get(room) || byRoom.get(room);
                if (!unit) {
                  return (
                    <div
                      key={room}
                      className="rent-map-cell is-missing"
                      aria-hidden
                      title="欠番"
                    >
                      <span className="rent-map-room">{room}</span>
                    </div>
                  );
                }
                const plan = unitRentPlan(unit);
                const cur = unitRentBreakdown(unit);
                const isSel = selectedId === unit.id;
                const mismatch =
                  cur.total_rent != null &&
                  plan.total_year2 != null &&
                  Math.abs(cur.total_rent - plan.total_year2) >= 1;
                return (
                  <button
                    key={room}
                    type="button"
                    className={[
                      "rent-map-cell",
                      unit.status === "vacant" ? "is-vacant" : "is-occupied",
                      isSel ? "is-selected" : "",
                      mismatch ? "is-mismatch" : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                    title={hoverTitle(unit)}
                    onClick={() => {
                      setSelectedId(unit.id);
                      setErr(null);
                      setOkMsg(null);
                    }}
                  >
                    <span className="rent-map-room">{unit.room}</span>
                    <span className="rent-map-status">
                      {unit.status === "vacant" ? "空室" : "入居"}
                      {mismatch ? " · 差あり" : ""}
                    </span>
                    <span className="rent-map-now">
                      現状 {fmtYen(cur.total_rent)}
                    </span>
                    <span className="rent-map-plan">
                      計画 {fmtYen(plan.total_year2)}
                    </span>
                    {plan.discount_yen != null && plan.discount_yen > 0 ? (
                      <span className="rent-map-disc">
                        1年目 {fmtDiscount(plan)}
                      </span>
                    ) : null}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {selected && selectedPlan && selectedCurrent ? (
        <aside
          className="rent-map-panel"
          aria-label={`${shortLabel(selected)} 詳細`}
        >
          <header className="rent-map-panel-head">
            <h4>
              {shortLabel(selected)}{" "}
              <span className="meta">
                {selected.status === "vacant" ? "空室" : "入居"}
                {managers[selected.room] ? ` · ${managers[selected.room]}` : ""}
              </span>
            </h4>
            <div className="rent-map-panel-actions">
              <button
                type="button"
                className="btn"
                onClick={() => setEditOpen((v) => !v)}
              >
                {editOpen ? "修正を閉じる" : "条件を修正"}
              </button>
              <button
                type="button"
                className="btn"
                onClick={() => setSelectedId(null)}
              >
                閉じる
              </button>
            </div>
          </header>

          <div className="rent-map-compare">
            <div>
              <div className="meta">現状</div>
              <div>
                家賃 {fmtYen(selectedCurrent.rent)} ＋ 管理費{" "}
                {fmtYen(selectedCurrent.management_fee)} ＝{" "}
                <strong>{fmtYen(selectedCurrent.total_rent)}</strong>
              </div>
            </div>
            <div>
              <div className="meta">計画・2年目以降</div>
              <div>
                家賃 {fmtYen(selectedPlan.rent_year2)} ＋ 管理費{" "}
                {fmtYen(selectedPlan.management_fee)} ＝{" "}
                <strong>{fmtYen(selectedPlan.total_year2)}</strong>
              </div>
            </div>
            <div>
              <div className="meta">1年目（キャンペーン）</div>
              <div>
                家賃 {fmtYen(selectedPlan.rent_year1)} ＝ 合計{" "}
                <strong>{fmtYen(selectedPlan.total_year1)}</strong>
                {" · "}
                {fmtDiscount(selectedPlan)}
                {selectedPlan.campaign_until
                  ? ` · 期限 ${selectedPlan.campaign_until}`
                  : ""}
              </div>
            </div>
          </div>

          {selectedPlan.plan_note ? (
            <p className="rent-map-plan-note">{selectedPlan.plan_note}</p>
          ) : null}

          {editOpen ? (
            <section className="rent-map-edit" aria-label="条件修正">
              <h5>条件を修正</h5>
              <p className="meta">
                差があるときはここで直します。保存するとメモ履歴にも残ります。
              </p>
              <div className="rent-map-edit-grid">
                <label>
                  <span className="meta">現状家賃</span>
                  <input
                    inputMode="numeric"
                    value={formRent}
                    onChange={(e) => setFormRent(e.target.value)}
                    disabled={pending}
                  />
                </label>
                <label>
                  <span className="meta">管理費</span>
                  <input
                    inputMode="numeric"
                    value={formMgmt}
                    onChange={(e) => setFormMgmt(e.target.value)}
                    disabled={pending}
                  />
                </label>
                <label>
                  <span className="meta">1年目家賃</span>
                  <input
                    inputMode="numeric"
                    value={formY1}
                    onChange={(e) => setFormY1(e.target.value)}
                    disabled={pending}
                  />
                </label>
                <label>
                  <span className="meta">2年目家賃（計画）</span>
                  <input
                    inputMode="numeric"
                    value={formY2}
                    onChange={(e) => setFormY2(e.target.value)}
                    disabled={pending}
                  />
                </label>
                <label>
                  <span className="meta">キャンペーン期限</span>
                  <input
                    value={formUntil}
                    onChange={(e) => setFormUntil(e.target.value)}
                    placeholder="例: 26/7 または 8月"
                    disabled={pending}
                  />
                </label>
                <label>
                  <span className="meta">状態</span>
                  <select
                    value={formStatus}
                    onChange={(e) =>
                      setFormStatus(
                        e.target.value === "vacant" ? "vacant" : "occupied",
                      )
                    }
                    disabled={pending}
                  >
                    <option value="occupied">入居</option>
                    <option value="vacant">空室</option>
                  </select>
                </label>
              </div>
              <label className="rent-map-memo-form">
                <span className="meta">修正理由（任意）</span>
                <input
                  value={formReason}
                  onChange={(e) => setFormReason(e.target.value)}
                  placeholder="例: 成約条件に合わせて現状を修正"
                  disabled={pending}
                />
              </label>
              <button
                type="button"
                className="btn"
                disabled={pending}
                onClick={() => void onSaveTerms()}
              >
                {pending ? "保存中…" : "条件を保存"}
              </button>
            </section>
          ) : null}

          <section className="rent-map-memos">
            <h5>メモ履歴</h5>
            {selectedPlan.memo_log.length === 0 ? (
              <p className="meta">まだありません</p>
            ) : (
              <ul>
                {[...selectedPlan.memo_log].reverse().map((m, i) => (
                  <li key={`${m.at}-${i}`}>
                    <span className="meta">
                      {fmtWhen(m.at)} · {m.source}
                    </span>
                    <div>{m.text}</div>
                  </li>
                ))}
              </ul>
            )}
            <label className="rent-map-memo-form">
              <span className="meta">メモを追記</span>
              <textarea
                rows={3}
                value={memoText}
                onChange={(e) => setMemoText(e.target.value)}
                placeholder="交渉メモ・内覧状況など"
                disabled={pending}
              />
            </label>
            {err ? <p className="rent-map-err">{err}</p> : null}
            {okMsg ? <p className="rent-map-ok">{okMsg}</p> : null}
            <button
              type="button"
              className="btn"
              disabled={pending || !memoText.trim()}
              onClick={() => void onAppendMemo()}
            >
              {pending ? "保存中…" : "追記する"}
            </button>
          </section>

          <section className="rent-map-events">
            <h5>空室／入居イベント</h5>
            {selectedEvents.length === 0 ? (
              <p className="meta">この号室の履歴はまだありません</p>
            ) : (
              <ul>
                {selectedEvents.slice(0, 12).map((ev) => (
                  <li key={ev.id}>
                    <span className="meta">
                      {ev.occurred_on} ·{" "}
                      {ev.event_type === "vacant" ? "空室" : "入居"}
                      {ev.source ? ` · ${ev.source}` : ""}
                    </span>
                    <div>{ev.note || ev.ref || "—"}</div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </aside>
      ) : (
        <p className="meta rent-map-hint">
          号室セルをクリックすると詳細・条件修正・メモ追記が開きます（ホバーで要約）。現状≠計画は「差あり」表示。
        </p>
      )}
    </div>
  );
}
