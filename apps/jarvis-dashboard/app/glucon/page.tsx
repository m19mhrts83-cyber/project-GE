import Shell from "@/components/Shell";
import FolderLinks from "@/components/FolderLinks";
import GluconArchiveList from "@/components/glucon/GluconArchiveList";
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
        神大家の月次活動報告・成果報告を、Journal・パートナーやり取り・モチベーション数値・入退去イベント（前回期限〜今回期限）とコミュニティ参考例からまとめ、確認後に WeStudy へ投稿します。
      </p>
      <FolderLinks links={folderLinks} />

      {state.loadError ? (
        <p className="qe-err">
          日程の自動取得で問題がありました（ページは続行できます）: {state.loadError}
        </p>
      ) : null}

      <GluconScheduleHeader cycle={state.cycle} />
      <GluconReportPanel
        cycle={state.cycle}
        drafts={state.drafts}
        journals={state.journals}
        journalSyncedAt={state.journalSyncedAt}
        memberHeader={state.memberHeader}
        monthlyDigest={state.monthlyDigest}
        lastResultCoverage={state.lastResultCoverage}
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
