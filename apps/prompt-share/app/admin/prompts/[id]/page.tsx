import { PromptEditor } from "@/components/PromptEditor";

type Props = { params: Promise<{ id: string }> };

export default async function EditPromptPage({ params }: Props) {
  const { id } = await params;
  return <PromptEditor promptId={Number(id)} />;
}
