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

export type GrokPillar = {
  id: string;
  name: string;
  role: string;
  note?: string;
};

export type GrokBot = {
  id: string;
  code: string;
  name: string;
  kind: string;
  work: string;
  schedule: string;
  drive_target: string;
  paste: string;
  department_id: string;
  department_name: string;
  channel: string;
  exec_level: string;
};

export type GrokDept = {
  id: string;
  name: string;
  channel: string;
  exec_level: string;
  bot_ids: string[];
  bot_count: number;
};

export type GrokMapping = {
  agent_id: string;
  agent_name: string;
  builder_tag: string;
  mixup_kind: string;
  grok_counterpart: string;
  grok_ids: string[];
  grok_labels: string[];
  role_split: string;
};

export type GrokPayload = {
  updated: string;
  index_doc?: string;
  mixup_doc?: string;
  pillars: GrokPillar[];
  departments: GrokDept[];
  bots: GrokBot[];
  mappings: GrokMapping[];
  note?: string;
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
  grok?: GrokPayload;
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

export function getGrok(): GrokPayload {
  return (
    getAgentTeam().grok || {
      updated: "",
      pillars: [],
      departments: [],
      bots: [],
      mappings: [],
    }
  );
}

export function getGrokBotById(id: string): GrokBot | undefined {
  return getGrok().bots.find((b) => b.id === id);
}

export function getMappingsForAgent(agentId: string): GrokMapping | undefined {
  return getGrok().mappings.find((m) => m.agent_id === agentId);
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

export function mixupKindLabel(kind: string): string {
  switch (kind) {
    case "mac_twin":
      return "Mac側ツイン";
    case "lane":
      return "ミックスレーン";
    case "none":
      return "対応なし";
    default:
      return kind || "—";
  }
}
