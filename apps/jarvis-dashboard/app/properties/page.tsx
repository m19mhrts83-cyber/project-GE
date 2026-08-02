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
import { fetchPropertyKeyNumbers } from "@/lib/notionPropertyKeys";
import {
  fmtKeyNumber,
  managersForProperty,
  resolveRoomManager,
} from "@/lib/propertyInfo";
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
  const propertyKeys = await fetchPropertyKeyNumbers();

  const { data: events } = await supabase
    .from("property_occupancy_events")
    .select(
      "id,occurred_on,event_type,property_id,property_name,room,source,ref,note",
    )
    .order("occurred_on", { ascending: false })
    .limit(80);
  const eventList = (events || []) as OccupancyEvent[];

  const allManagers = [
    ...new Set(
      groups.flatMap((g) =>
        managersForProperty(
          g.property_id,
          g.units.map((u) => ({ room: u.room, note: u.note })),
        ),
      ),
    ),
  ];

  return (
    <TriageKanbanLane
      lane="properties"
      title="所有物件"
      active="/properties"
      subtitle="号室ごとに家賃・管理費・管理会社・空室時鍵番号。建物ごとの合計も表示。"
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

      <section className="prop-mgmt-summary" aria-label="管理会社一覧">
        <h2>管理会社一覧</h2>
        {allManagers.length === 0 ? (
          <p className="empty">未設定</p>
        ) : (
          <ul className="prop-mgmt-list">
            {allManagers.map((m) => {
              const buildings = groups
                .filter((g) =>
                  managersForProperty(
                    g.property_id,
                    g.units.map((u) => ({ room: u.room, note: u.note })),
                  ).includes(m),
                )
                .map((g) => g.property_name);
              return (
                <li key={m}>
                  <strong>{m}</strong>
                  <span className="meta"> — {buildings.join("、")}</span>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <h2>号室一覧（建物別）</h2>
      {units.length === 0 ? (
        <p className="empty">
          未取込です。Excel から{" "}
          <code>jarvis_property_occupancy_from_excel.py --push</code>
        </p>
      ) : (
        groups.map((g) => {
          const mgrs = managersForProperty(
            g.property_id,
            g.units.map((u) => ({ room: u.room, note: u.note })),
          );
          const key = propertyKeys.keys[g.property_id];
          return (
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
                  {" · 管理 "}
                  {mgrs.length ? mgrs.join(" / ") : "—"}
                  {" · 空室時鍵番号 "}
                  <strong>{fmtKeyNumber(key)}</strong>
                </div>
              </div>
              <div className="home-unit-table-wrap">
                <table className="home-unit-table">
                  <thead>
                    <tr>
                      <th>ラベル</th>
                      <th>号室</th>
                      <th>状態</th>
                      <th>管理会社</th>
                      <th>家賃</th>
                      <th>管理費</th>
                      <th>賃料合計</th>
                      <th>メモ</th>
                    </tr>
                  </thead>
                  <tbody>
                    {g.units.map((u) => {
                      const b = unitRentBreakdown(u);
                      const mgr = resolveRoomManager(
                        g.property_id,
                        u.room,
                        u.note,
                      );
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
                          <td>{mgr || "—"}</td>
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
                      <td colSpan={4}>建物合計</td>
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
          );
        })
      )}

      {propertyKeys.source === "yaml_cache" ? (
        <p className="meta">
          鍵番号は{" "}
          <a href={propertyKeys.boardUrl} target="_blank" rel="noreferrer">
            Notion DB_物件情報
          </a>{" "}
          のキャッシュ表示
          {propertyKeys.reason ? `（${propertyKeys.reason}）` : ""}
          。Integration に DB を接続すると自動更新されます。
        </p>
      ) : (
        <p className="meta">
          鍵番号: Notion{" "}
          <a href={propertyKeys.boardUrl} target="_blank" rel="noreferrer">
            DB_物件情報
          </a>{" "}
          から取得
        </p>
      )}

      <h2>空室／入居履歴</h2>
      {eventList.length === 0 ? (
        <p className="empty">履歴はまだありません（メール検知後に増えます）</p>
      ) : (
        <div className="prop-event-table-wrap" role="region" aria-label="空室入居履歴">
          <table className="prop-event-table">
            <thead>
              <tr>
                <th>日付</th>
                <th>区分</th>
                <th>物件</th>
                <th>号室</th>
                <th>ソース</th>
                <th>参照</th>
                <th>メモ</th>
              </tr>
            </thead>
            <tbody>
              {eventList.map((ev) => (
                <tr key={ev.id}>
                  <td>{ev.occurred_on}</td>
                  <td>
                    <span
                      className={
                        ev.event_type === "vacant"
                          ? "prop-event-type is-vacant"
                          : "prop-event-type is-occupied"
                      }
                    >
                      {ev.event_type === "vacant" ? "空室" : "入居"}
                    </span>
                  </td>
                  <td>{ev.property_name || ev.property_id}</td>
                  <td>{ev.room}</td>
                  <td className="meta">{ev.source || "—"}</td>
                  <td className="meta">{ev.ref || "—"}</td>
                  <td className="prop-note">{ev.note || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="sub" style={{ marginTop: 8 }}>
        <Link href="/metrics">収支・数値 →</Link>
      </p>
    </TriageKanbanLane>
  );
}
