import { setTriageStatus } from "@/app/actions/archive";

type Props = {
  id: string;
  status: string;
  path: string;
};

export default function TriageDoneToggle({ id, status, path }: Props) {
  const done = status === "done";
  const next = done ? ("pending" as const) : ("done" as const);
  const label = done ? "pendingに戻す" : "対応済み";
  const action = setTriageStatus.bind(null, id, next, path);

  return (
    <form action={action} style={{ marginLeft: "auto" }}>
      <button
        type="submit"
        className="btn"
        style={{ padding: "4px 10px", fontSize: "0.78rem" }}
      >
        {label}
      </button>
    </form>
  );
}
