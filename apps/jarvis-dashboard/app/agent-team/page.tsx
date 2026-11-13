import Shell from "@/components/Shell";
import { Suspense } from "react";
import AgentTeamClient from "@/components/agent-team/AgentTeamClient";
import MaturityPanel from "@/components/agent-team/MaturityPanel";
import {
  getAgentTeam,
  getGenres,
  getGrok,
  getOpsMeta,
  getPermissionsMeta,
} from "@/lib/agentTeam";

export const dynamic = "force-dynamic";

export default function AgentTeamPage() {
  const team = getAgentTeam();
  const grok = getGrok();
  const genres = getGenres();
  const permissionsMeta = getPermissionsMeta();
  const opsMeta = getOpsMeta();

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
        opsMeta={opsMeta}
        maturity={
          <Suspense fallback={<p className="meta">成熟度を読み込み中…</p>}>
            <MaturityPanel />
          </Suspense>
        }
      />
    </Shell>
  );
}
