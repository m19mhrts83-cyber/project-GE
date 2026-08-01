import Link from "next/link";
import TriageKanbanLane from "@/components/TriageKanbanLane";
import {
  fmtYen,
  shortLabel,
  summarizeUnits,
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
      subtitle="満室状況の下に処置候補 → Notion「所有物件タスク管理」看板へ。"
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
      </div>

      <h2>号室一覧</h2>
      {units.length === 0 ? (
        <p className="empty">
          未取込です。Excel から{" "}
          <code>jarvis_property_occupancy_from_excel.py --push</code>
        </p>
      ) : (
        <div className="home-unit-table-wrap">
          <table className="home-unit-table">
            <thead>
              <tr>
                <th>ラベル</th>
                <th>物件</th>
                <th>号室</th>
                <th>状態</th>
                <th>家賃</th>
                <th>メモ</th>
              </tr>
            </thead>
            <tbody>
              {units.map((u) => (
                <tr
                  key={u.id}
                  className={u.status === "vacant" ? "is-vacant" : undefined}
                >
                  <td>{shortLabel(u)}</td>
                  <td>{u.property_name}</td>
                  <td>{u.room}</td>
                  <td>{u.status === "vacant" ? "空室" : "入居"}</td>
                  <td>{fmtYen(u.rent)}</td>
                  <td>{u.note || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
        <Link href="/metrics">財務メトリクス →</Link>
      </p>
    </TriageKanbanLane>
  );
}
