/** MQページ · レーン（MQ会計表 / 資金繰り表） */

export type MqView = "mq" | "cashflow";

const LANES: { id: MqView; label: string; hint: string }[] = [
  { id: "mq", label: "MQ会計表", hint: "PQ / VQ / F / G の年次評価" },
  { id: "cashflow", label: "資金繰り表", hint: "月次の入出金推移（MG形式）" },
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
