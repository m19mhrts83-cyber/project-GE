import Link from "next/link";
import DraftReviewClient from "@/components/DraftReviewClient";
import Icon from "@/components/Icon";

export const dynamic = "force-dynamic";

export default async function DraftPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <main>
      <div className="top">
        <Link className="back" href="/drafts" aria-label="一覧へ戻る">
          <Icon name="back" size={22} />
        </Link>
        <div className="grow">
          <div className="eyebrow acc">DRAFT ／ 直す → 差分</div>
          <h1>下書きを直す</h1>
        </div>
      </div>
      <DraftReviewClient id={id} />
    </main>
  );
}
