import Shell from "@/components/Shell";
import AgentTeamClient from "@/components/agent-team/AgentTeamClient";
import {
  getAgentTeam,
  getGenres,
  getGrok,
  getPermissionsMeta,
} from "@/lib/agentTeam";

export default function AgentTeamPage() {
  const team = getAgentTeam();
  const grok = getGrok();
  const genres = getGenres();
  const permissionsMeta = getPermissionsMeta();

  return (
    <Shell active="/agent-team">
      <h1>AIエージェントチーム</h1>
      <AgentTeamClient
        departments={team.departments}
        agents={team.agents}
        genres={genres}
        genreNote={team.genre_note}
        counts={team.counts}
        updated={team.updated}
        flowforgeNote={team.flowforge_open_note}
        builderUrl={team.builder.url}
        builderTitle={team.builder.title}
        grok={grok}
        permissionsMeta={permissionsMeta}
        permissionsUpdated={team.permissions_updated}
      />
    </Shell>
  );
}
