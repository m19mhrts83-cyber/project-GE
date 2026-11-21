/**
 * agentId（"315" や "315-B"）→ FlowForge のフロー参照。
 * 1社員に複数フローがある時は、registry の extra_flows に "315-B" のように登録する。
 * 純関数のみ（テストしやすいよう Next 依存なし）。agentId の形式は flowforgeEditView.ts の AGENT_ID_RE。
 */
export type FlowRef = {
  agentId: string;
  flowforge_id: string;
  flowforge_url?: string;
  flowforge_share_url?: string;
};

type ExtraFlow = {
  id: string;
  flowforge_id?: string;
  flowforge_url?: string;
  flowforge_share_url?: string;
};

type AgentLike = {
  id: string;
  flowforge_id?: string;
  flowforge_url?: string;
  flowforge_share_url?: string;
  extra_flows?: ExtraFlow[];
};

/** 本体（315）は社員行、枝（315-B）は extra_flows から探す。未登録は undefined。 */
export function findFlowRef(agents: AgentLike[], agentId: string): FlowRef | undefined {
  for (const a of agents) {
    if (a.id === agentId) {
      return a.flowforge_id
        ? {
            agentId,
            flowforge_id: a.flowforge_id,
            flowforge_url: a.flowforge_url,
            flowforge_share_url: a.flowforge_share_url,
          }
        : undefined;
    }
    const x = (a.extra_flows || []).find((f) => f.id === agentId);
    if (x?.flowforge_id) return { agentId, ...x, flowforge_id: x.flowforge_id };
  }
  return undefined;
}

/** flowId から探す（本体・枝の両方）。 */
export function findFlowRefByFlowId(agents: AgentLike[], flowId: string): FlowRef | undefined {
  for (const a of agents) {
    if (a.flowforge_id === flowId) return findFlowRef(agents, a.id);
    const x = (a.extra_flows || []).find((f) => f.flowforge_id === flowId);
    if (x) return findFlowRef(agents, x.id);
  }
  return undefined;
}
