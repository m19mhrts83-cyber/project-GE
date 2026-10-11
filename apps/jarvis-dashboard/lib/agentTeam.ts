import data from "@/data/agentTeam.json";

export type AgentStatus = "候補" | "設計中" | "運用確認" | "運用" | "停止" | string;

export type AgentTeamAgent = {
  id: string;
  name: string;
  path: string;
  department_id: string;
  department_name: string;
  status: AgentStatus;
  status_icon: string;
  report: string;
  trigger: string;
  schedule: string;
  tool_assigned: string;
  tool_fit: string;
  tool_notes: string;
  note: string;
  summary: string;
  flow_summary: string;
  builder_tag: string;
  mixup_kind: string;
  grok_counterpart: string;
  flowforge_id: string;
  flowforge_url: string;
};

export type AgentTeamDept = {
  id: string;
  name: string;
  path: string;
};

export type AgentTeamPayload = {
  updated: string;
  registry_updated: string;
  flowforge_base: string;
  flowforge_login_hint: string;
  flowforge_open_note: string;
  builder: { title: string; url: string; share_id: string };
  counts: Record<string, number>;
  departments: AgentTeamDept[];
  agents: AgentTeamAgent[];
};

const STATUS_RANK: Record<string, number> = {
  運用確認: 0,
  設計中: 1,
  運用: 2,
  候補: 3,
  停止: 4,
};

export function getAgentTeam(): AgentTeamPayload {
  return data as AgentTeamPayload;
}

export function getAgentById(id: string): AgentTeamAgent | undefined {
  return getAgentTeam().agents.find((a) => a.id === id);
}

export function sortAgents(agents: AgentTeamAgent[]): AgentTeamAgent[] {
  return agents.slice().sort((a, b) => {
    const ra = STATUS_RANK[a.status] ?? 9;
    const rb = STATUS_RANK[b.status] ?? 9;
    if (ra !== rb) return ra - rb;
    return a.id.localeCompare(b.id, "ja");
  });
}

export function reportLabel(report: string): string {
  if (!report) return "—";
  if (report.startsWith("#")) return report;
  return `#${report}`;
}

export function statusClass(status: string): string {
  switch (status) {
    case "運用":
      return "at-st at-st-run";
    case "運用確認":
      return "at-st at-st-check";
    case "設計中":
      return "at-st at-st-design";
    case "停止":
      return "at-st at-st-stop";
    default:
      return "at-st at-st-cand";
  }
}
