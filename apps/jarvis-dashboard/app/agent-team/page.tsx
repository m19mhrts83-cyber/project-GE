import Shell from "@/components/Shell";
import AgentTeamClient from "@/components/agent-team/AgentTeamClient";
import { getAgentTeam, getGrok } from "@/lib/agentTeam";

export default function AgentTeamPage() {
  const team = getAgentTeam();
  const grok = getGrok();

  return (
    <Shell active="/agent-team">
      <h1>AIエージェントチーム</h1>
      <AgentTeamClient
        departments={team.departments}
        agents={team.agents}
        counts={team.counts}
        updated={team.updated}
        flowforgeNote={team.flowforge_open_note}
        builderUrl={team.builder.url}
        builderTitle={team.builder.title}
        grok={grok}
      />
    </Shell>
  );
}
