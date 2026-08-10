import { PromptListClient } from "@/components/PromptListClient";

type Props = { params: Promise<{ slug: string }> };

export default async function GroupPage({ params }: Props) {
  const { slug } = await params;
  return <PromptListClient groupSlug={slug} />;
}
