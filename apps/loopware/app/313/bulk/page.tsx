import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

/** 「まとめて片付ける」は 313 の既定の画面になった。古いリンク（Slack など）はここから 313 へ */
export default function CleanupBulkPage() {
  redirect("/313");
}
