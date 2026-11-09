import Link from "next/link";
import DraftsClient from "@/components/DraftsClient";
import Icon from "@/components/Icon";

export const dynamic = "force-dynamic";

export default function DraftsPage() {
  return (
    <main>
      <div className="top">
        <Link className="back" href="/" aria-label="ハブへ戻る">
          <Icon name="back" size={22} />
        </Link>
        <div className="grow">
          <div className="eyebrow acc">DRAFTS ／ 下書きを直す</div>
          <h1>箇所を選んで、声でダメ出し</h1>
        </div>
      </div>
      <DraftsClient />
    </main>
  );
}
