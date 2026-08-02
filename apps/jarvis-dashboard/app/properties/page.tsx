import Link from "next/link";
import TriageKanbanLane from "@/components/TriageKanbanLane";
import {
  fmtYen,
  groupUnitsByProperty,
  shortLabel,
  summarizeUnits,
  unitRentBreakdown,
  type OccupancyEvent,
  type PropertyUnit,
} from "@/lib/occupancy";
import { createClient } from "@/lib/supabase/server";

export default async function Page() {
  const supabase = await createClient();

  const { data: unitRows } = await supabase
    .from("property_units")
    .select(
      "id,property_id,property_name,room,status,rent,note,source,payload,updated_at",
    )
    .order("property_id")
    .order("room");
  const units = (unitRows || []) as PropertyUnit[];
  const summary = summarizeUnits(units);
  const groups = groupUnitsByProperty(units);
  const allTotalRent = groups.reduce((s, g) => s + g.total_rent_sum, 0);

  const { data: events } = await supabase
    .from("property_occupancy_events")
    .select(
      "id,occurred_on,event_type,property_id,property_name,room,source,ref,note",
    )
    .order("occurred_on", { ascending: false })
    .limit(80);
  const eventList = (events || []) as OccupancyEvent[];

  return (
    <TriageKanbanLane
      lane="properties"
      title="所有物件"
      active="/properties"
      subtitle="号室ごとに家賃・管理費・賃料合計とメモ。建物ごとの合計も表示。"
    >
      <div className="stats">
        <div className="stat">
          全体満室率{" "}
          <strong>{summary.total ? `${summary.rate_pct}%` : "—"}</strong>
        </div>
        <div className="stat">
          入居 <strong>{summary.occupied}</strong> / {summary.total || "—"}
        </div>
        <div className="stat">
          空室{" "}
          <strong>
            {summary.vacant_labels.length
              ? summary.vacant_labels.join("、")
              : "なし"}
          </strong>
        </div>
        <div className="stat">
          全物件・賃料合計 <strong>{fmtYen(allTotalRent || null)}</strong>
        </div>
      </div>

      <h2>号室一覧（建物別）</h2>
      {units.length === 0 ? (
        <p className="empty">
          未取込です。Excel から{" "}
          <code>jarvis_property_occupancy_from_excel.py --push</code>
        </p>
      ) : (
        groups.map((g) => (
          <section key={g.property_id} className="prop-block">
            <div className="prop-block-head">
              <h3 className="prop-block-title">{g.property_name}</h3>
              <div className="prop-block-meta">
                入居 {g.occupied}/{g.units.length}
                {" · "}
                賃料合計 <strong>{fmtYen(g.total_rent_sum || null)}</strong>
                {" （家賃 "}
                {fmtYen(g.rent_sum || null)}
                {" ＋ 管理費 "}
                {fmtYen(g.mgmt_sum || null)}
                {"）"}
              </div>
            </div>
            <div className="home-unit-table-wrap">
              <table className="home-unit-table">
                <thead>
                  <tr>
                    <th>ラベル</th>
                    <th>号室</th>
                    <th>状態</th>
                    <th>家賃</th>
                    <th>管理費</th>
                    <th>賃料合計</th>
                    <th>メモ</th>
                  </tr>
                </thead>
                <tbody>
                  {g.units.map((u) => {
                    const b = unitRentBreakdown(u);
                    return (
                      <tr
                        key={u.id}
                        className={
                          u.status === "vacant" ? "is-vacant" : undefined
                        }
                      >
                        <td>{shortLabel(u)}</td>
                        <td>{u.room}</td>
                        <td>{u.status === "vacant" ? "空室" : "入居"}</td>
                        <td>{fmtYen(b.rent)}</td>
                        <td>{fmtYen(b.management_fee)}</td>
                        <td>
                          <strong>{fmtYen(b.total_rent)}</strong>
                        </td>
                        <td className="prop-note">{u.note || "—"}</td>
                      </tr>
                    );
                  })}
                  <tr className="prop-total-row">
                    <td colSpan={3}>建物合計</td>
                    <td>{fmtYen(g.rent_sum || null)}</td>
                    <td>{fmtYen(g.mgmt_sum || null)}</td>
                    <td>
                      <strong>{fmtYen(g.total_rent_sum || null)}</strong>
                    </td>
                    <td />
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        ))
      )}

      <h2>空室／入居履歴</h2>
      {eventList.length === 0 ? (
        <p className="empty">履歴はまだありません（メール検知後に増えます）</p>
      ) : (
        <ul className="home-event-list">
          {eventList.map((ev) => (
            <li key={ev.id}>
              <strong>{ev.occurred_on}</strong>{" "}
              {ev.event_type === "vacant" ? "空室" : "入居"}{" "}
              {ev.property_name || ev.property_id}-{ev.room}
              {ev.source ? ` · ${ev.source}` : ""}
              {ev.ref ? ` · ${ev.ref}` : ""}
            </li>
          ))}
        </ul>
      )}

      <p className="sub" style={{ marginTop: 8 }}>
        <Link href="/metrics">収支・数値 →</Link>
      </p>
    </TriageKanbanLane>
  );
}
