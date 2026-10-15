import data from "@/data/agentTeam.json";

export type AgentStatus = "候補" | "設計中" | "運用確認" | "運用" | "停止" | string;

export type PermissionMethod = {
  name: string;
  level: string;
  detail: string;
};

export type SiteLogin = {
  service: string;
  access?: string;
  note?: string;
};

export type AgentPermissions = {
  can_do: string;
  methods: PermissionMethod[];
  methods_filled: boolean;
  env_keys: string[];
  site_logins: SiteLogin[];
  site_logins_summary: string;
  has_site_logins: boolean;
  human_gate: string;
  secrets_note?: string;
  source?: string;
};

export type BotPermissions = {
  can_do: string;
  exec_level: string;
  secrets_policy: string;
  secrets_note?: string;
  site_logins: SiteLogin[];
  site_logins_summary: string;
  has_site_logins: boolean;
  human_gate: string;
  source?: string;
};

export type PermissionsMeta = {
  defaults?: {
    ai?: { human_gate?: string; secrets_note?: string };
    grok?: {
      secrets_policy?: string;
      secrets_note?: string;
      human_gate?: string;
    };
  };
  site_login_agent_ids?: string[];
  site_login_bot_ids?: string[];
  doc?: string;
  yaml?: string;
  note?: string;
};

export type AgentTeamAgent = {
  id: string;
  name: string;
  path: string;
  department_id: string;
  department_name: string;
  genre_id?: string;
  genre_name?: string;
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
  flowforge_share_url?: string;
  flowforge_edit_url?: string;
  permissions?: AgentPermissions;
};

export type AgentTeamDept = {
  id: string;
  name: string;
  path: string;
  genre_id?: string;
  genre_name?: string;
};

export type AgentTeamGenre = {
  id: string;
  name: string;
  order: number;
  summary: string;
  leaders: { grok: string; ai: string };
  ai_department_ids: string[];
  grok_department_ids: string[];
  nav_hints: string[];
  ai_agent_ids: string[];
  grok_bot_ids: string[];
  counts: {
    ai: number;
    grok: number;
    paired: number;
    ai_only: number;
    grok_only: number;
  };
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
  genre_id?: string;
  genre_name?: string;
  permissions?: BotPermissions;
};

export type GrokDept = {
  id: string;
  name: string;
  channel: string;
  exec_level: string;
  bot_ids: string[];
  bot_count: number;
  genre_id?: string;
  genre_name?: string;
};

export type GrokMappingSide = "paired" | "ai_only" | "grok_only" | string;

export type GrokMapping = {
  side: GrokMappingSide;
  agent_id: string;
  agent_name: string;
  builder_tag: string;
  mixup_kind: string;
  grok_counterpart: string;
  grok_ids: string[];
  grok_labels: string[];
  grok_department?: string;
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
  mapping_counts?: {
    paired: number;
    ai_only: number;
    grok_only: number;
    all: number;
  };
  note?: string;
};

export type AgentTeamPayload = {
  updated: string;
  registry_updated: string;
  permissions_updated?: string;
  flowforge_base: string;
  flowforge_login_hint: string;
  flowforge_login_email?: string;
  flowforge_open_note: string;
  builder: { title: string; url: string; share_id: string };
  counts: Record<string, number>;
  genres?: AgentTeamGenre[];
  genre_note?: string;
  departments: AgentTeamDept[];
  agents: AgentTeamAgent[];
  grok?: GrokPayload;
  permissions_meta?: PermissionsMeta;
};

export function getPermissionsMeta(): PermissionsMeta {
  return getAgentTeam().permissions_meta || {};
}

export function permissionLevelClass(level: string): string {
  const t = (level || "").trim();
  if (t === "○" || t === "✅" || t === "〇") return "at-perm-ok";
  if (t === "△") return "at-perm-mid";
  if (t === "×" || t === "✕" || t === "✗") return "at-perm-no";
  return "";
}

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

export function getGenres(): AgentTeamGenre[] {
  const list = getAgentTeam().genres || [];
  return list.slice().sort((a, b) => (a.order ?? 99) - (b.order ?? 99));
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
    case "ai_only":
      return "AI社員のみ";
    case "grok_only":
      return "Grokのみ";
    case "none":
      return "対応なし";
    default:
      return kind || "—";
  }
}

/** 対応表・詳細で種別の読み方を補足する短文 */
export function mixupKindHint(kind: string): string {
  switch (kind) {
    case "mac_twin":
      return "実行の正＝対応Grok。このAI社員＝見守り・検収・補給・Slack（同じ仕事の二重実行はしない）";
    case "lane":
      return "特定Botの代替ではない。両系統の材料を並べて比較するレーン";
    case "ai_only":
      return "対応するGrok同型なし（Jarvis／Slack／Mac本線）";
    case "grok_only":
      return "対応するAI社員なし（Grok側のみ）";
    default:
      return "";
  }
}

export function mappingSideLabel(side: string): string {
  switch (side) {
    case "paired":
      return "対応あり";
    case "ai_only":
      return "AIのみ";
    case "grok_only":
      return "Grokのみ";
    default:
      return side || "—";
  }
}

/** 外部ブラウザ向け。共有があれば閲覧URL、なければ編集（AccountChooser） */
export function flowforgeOpenUrl(agent: AgentTeamAgent): string {
  return (
    agent.flowforge_share_url ||
    agent.flowforge_edit_url ||
    agent.flowforge_url ||
    ""
  );
}

export function flowforgeOpenLabel(agent: AgentTeamAgent): string {
  if (agent.flowforge_share_url) return "閲覧で開く";
  if (agent.flowforge_edit_url || agent.flowforge_url) return "編集で開く（m19m）";
  return "—";
}
