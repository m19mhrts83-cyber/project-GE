/** MQページ · レーン（MQ会計表 / 資金繰り表） */

export type MqView = "mq" | "cashflow" | "reconcile";

const LANES: { id: MqView; label: string; hint: string }[] = [
  { id: "mq", label: "MQ会計表", hint: "PQ / VQ / F / G の年次評価（L2）" },
  { id: "cashflow", label: "資金繰り表", hint: "帳簿・月次の入出金推移（L1）" },
  { id: "reconcile", label: "整合", hint: "資金繰り vs MQ / B/S の差分" },
];

export default function MqLaneNav({
  active,
  hrefFor,
}: {
  active: MqView;
  hrefFor: (view: MqView) => string;
}) {
  return (
    <nav
      aria-label="MQレーン"
      className="mq-lane-nav"
    >
      <span className="meta mq-lane-nav-label">レーン</span>
      {LANES.map((l) => {
        const on = l.id === active;
        return (
          <a
            key={l.id}
            href={hrefFor(l.id)}
            className={on ? "btn primary mq-lane-btn" : "mq-lane-btn mq-lane-btn-off"}
            title={l.hint}
          >
            {l.label}
          </a>
        );
      })}
    </nav>
  );
}
