import Link from "next/link";
import Icon from "@/components/Icon";
import CleanupBulkClient from "@/components/CleanupBulkClient";

export const dynamic = "force-dynamic";

export default function CleanupBulkPage() {
  return (
    <main className="wk-main">
      <div className="top">
        <Link className="back" href="/313" aria-label="313へ戻る">
          <Icon name="back" size={22} />
        </Link>
        <div className="grow">
          <div className="eyebrow acc">313 ／ 出口</div>
          <h1>まとめて片付ける</h1>
        </div>
      </div>
      <CleanupBulkClient />
    </main>
  );
}
