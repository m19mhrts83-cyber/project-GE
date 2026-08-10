import { PublicPromptClient } from "@/components/PublicPromptClient";

type Props = { params: Promise<{ token: string }> };

export default async function PublicPromptPage({ params }: Props) {
  const { token } = await params;
  return <PublicPromptClient token={token} />;
}
