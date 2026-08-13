"use client";

import { useMemo, useState } from "react";
import { appendPropertyUnitMemo } from "@/app/actions/propertyUnitMemo";
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
  const [localUnits, setLocalUnits] = useState(units);

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

  if (!layout) return null;

  async function onAppendMemo() {
    if (!selected) return;
    setPending(true);
    setErr(null);
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
  }

  return (
    <div className="rent-map">
      <div className="rent-map-floors" role="group" aria-label={`${propertyName} 家賃マップ`}>
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
                return (
                  <button
                    key={room}
                    type="button"
                    className={[
                      "rent-map-cell",
                      unit.status === "vacant" ? "is-vacant" : "is-occupied",
                      isSel ? "is-selected" : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                    title={hoverTitle(unit)}
                    onClick={() => {
                      setSelectedId(unit.id);
                      setErr(null);
                    }}
                  >
                    <span className="rent-map-room">{unit.room}</span>
                    <span className="rent-map-status">
                      {unit.status === "vacant" ? "空室" : "入居"}
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
        <aside className="rent-map-panel" aria-label={`${shortLabel(selected)} 詳細`}>
          <header className="rent-map-panel-head">
            <h4>
              {shortLabel(selected)}{" "}
              <span className="meta">
                {selected.status === "vacant" ? "空室" : "入居"}
                {managers[selected.room] ? ` · ${managers[selected.room]}` : ""}
              </span>
            </h4>
            <button
              type="button"
              className="btn"
              onClick={() => setSelectedId(null)}
            >
              閉じる
            </button>
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
        <p className="meta rent-map-hint">号室セルをクリックすると詳細・メモ追記が開きます（ホバーで要約）。</p>
      )}
    </div>
  );
}
