import { createClient } from "@/lib/supabase/server";
import ShellFrame from "@/components/ShellFrame";
import { fetchNavCounts } from "@/lib/navCounts";

export default async function Shell({
  children,
  active,
}: {
  children: React.ReactNode;
  active: string;
}) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  const counts = await fetchNavCounts();

  return (
    <ShellFrame
      active={active}
      email={user?.email ?? null}
      counts={counts}
    >
      {children}
    </ShellFrame>
  );
}
