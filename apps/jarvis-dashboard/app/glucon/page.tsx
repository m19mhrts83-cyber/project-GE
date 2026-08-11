import Shell from "@/components/Shell";
import FolderLinks from "@/components/FolderLinks";
import GluconArchiveList from "@/components/glucon/GluconArchiveList";
import GluconCarryMemoPanel from "@/components/glucon/GluconCarryMemoPanel";
import GluconMotivationPanel from "@/components/glucon/GluconMotivationPanel";
import GluconReportPanel from "@/components/glucon/GluconReportPanel";
import GluconScheduleHeader from "@/components/glucon/GluconScheduleHeader";
import { getGluconPageState } from "@/app/actions/glucon";
import { getFolderLinks, pageFolderKey } from "@/lib/folderLinks";
import {
  buildGluconMotivation,
  groupArchiveByPeriod,
} from "@/lib/glucon/stats";

export const maxDuration = 120;

export default async function GluconPage() {
  const state = await getGluconPageState();
  const folderLinks = getFolderLinks(pageFolderKey("glucon"));

  return (
    <Shell active="/glucon">
      <h1>グルコン報告</h1>
      <p className="meta">
        定常は活動報告です。前回投稿以降の進展を Journal・パートナーやり取り・数値・入退去から下書きし、確認後に WeStudy へ投稿します。成果報告は大きな区切りのときだけ使います。
      </p>
      <FolderLinks links={folderLinks} />

      {state.loadError ? (
        <p className="qe-err">
          日程の自動取得で問題がありました（ページは続行できます）: {state.loadError}
        </p>
      ) : null}

      <GluconScheduleHeader
        cycle={state.cycle}
        nextCycleHint={state.nextCycleHint}
      />
      <GluconCarryMemoPanel
        memos={state.carryMemos}
        periodKey={state.cycle?.periodKey || null}
      />
      <GluconReportPanel
        cycle={state.cycle}
        drafts={state.drafts}
        journals={state.journals}
        journalSyncedAt={state.journalSyncedAt}
        memberHeader={state.memberHeader}
        monthlyDigest={state.monthlyDigest}
        lastResultCoverage={state.lastResultCoverage}
        lastActivityCoverage={state.lastActivityCoverage}
        today={state.today}
      />
      <GluconMotivationPanel
        stats={buildGluconMotivation({
          drafts: state.archiveDrafts,
          currentPeriodKey: state.cycle?.periodKey || null,
          today: state.today,
          reportDeadline: state.cycle?.reportDeadline || null,
        })}
      />
      <GluconArchiveList months={groupArchiveByPeriod(state.archiveDrafts)} />
    </Shell>
  );
}
