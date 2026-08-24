/** MQページ · レーン（MQ会計表 / 資金繰り表 / 事業BS・PL） */

export type MqView = "mq" | "cashflow" | "reconcile" | "trends" | "re-pl";

const LANES: { id: MqView; label: string; hint: string }[] = [
  { id: "mq", label: "MQ会計表", hint: "PQ / VQ / F / G の年次評価（L2）" },
  { id: "cashflow", label: "資金繰り表", hint: "帳簿・月次の入出金推移（L1）" },
  {
    id: "re-pl",
    label: "事業BS・PL",
    hint: "ゼミ準拠の不動産事業評価（減価償却・利息・税）",
  },
  { id: "reconcile", label: "整合", hint: "資金繰り vs MQ / B/S の差分" },
  { id: "trends", label: "推移", hint: "自己資本の年次グラフ（MQ指標表は準備中）" },
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
