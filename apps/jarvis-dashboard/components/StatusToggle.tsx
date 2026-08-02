import { setCardStatus, setWatchStatus } from "@/app/actions/archive";

type Props = {
  table: "cards" | "watch_status";
  id: string;
  status: string;
  path: string;
  neverArchive?: boolean;
};

export default function StatusToggle({
  table,
  id,
  status,
  path,
  neverArchive,
}: Props) {
  if (neverArchive) {
    return (
      <span
        className="meta"
        style={{ marginLeft: "auto", fontSize: "0.78rem" }}
      >
        常駐
      </span>
    );
  }
  const archived = status === "archived";
  const next = archived ? ("active" as const) : ("archived" as const);
  const label = archived ? "再表示" : "アーカイブ";
  const action =
    table === "cards"
      ? setCardStatus.bind(null, id, next, path)
      : setWatchStatus.bind(null, id, next, path);

  return (
    <form action={action} style={{ marginLeft: "auto" }}>
      <button
        type="submit"
        className="btn"
        style={{ padding: "4px 10px", fontSize: "0.78rem", color: "var(--ink)" }}
      >
        {label}
      </button>
    </form>
  );
}
