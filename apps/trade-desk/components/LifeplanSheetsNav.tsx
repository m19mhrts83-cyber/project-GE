export default function LifeplanSheetsNav({
  current,
}: {
  current: "century" | "budget" | "abg";
}) {
  const items = [
    { id: "century" as const, href: "/lifeplan", label: "100歳計画" },
    { id: "budget" as const, href: "/lifeplan/budget", label: "予算編成" },
    { id: "abg" as const, href: "/lifeplan/abg", label: "支出の見方" },
  ];
  return (
    <nav className="lp-sheets" aria-label="ライフプランのシート">
      {items.map((it) => (
        <a
          key={it.id}
          href={it.href}
          className={`lp-sheet${current === it.id ? " active" : ""}`}
        >
          {it.label}
        </a>
      ))}
    </nav>
  );
}
