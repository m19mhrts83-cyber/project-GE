import { createClient } from "@/lib/supabase/server";
import { guessMime } from "@/lib/taxEvidence";
import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type EvidenceFile = {
  storage_path: string | null;
  stored_path: string;
  original_filename: string | null;
};

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const { data, error } = await supabase
    .from("kurashift_tax_evidence")
    .select("storage_path, stored_path, original_filename")
    .eq("id", id)
    .maybeSingle();
  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  const row = data as EvidenceFile | null;
  if (!row) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }

  const filename = row.original_filename || row.stored_path.split("/").pop() || "file";
  const mime = guessMime(filename);

  if (row.storage_path) {
    const signed = await supabase.storage
      .from("kurashift-tax")
      .createSignedUrl(row.storage_path, 120);
    if (signed.data?.signedUrl) {
      return NextResponse.redirect(signed.data.signedUrl);
    }
  }

  if (row.stored_path && existsSync(row.stored_path)) {
    const buf = await readFile(row.stored_path);
    return new NextResponse(buf, {
      headers: {
        "Content-Type": mime,
        "Content-Disposition": `inline; filename*=UTF-8''${encodeURIComponent(filename)}`,
        "Cache-Control": "private, max-age=60",
      },
    });
  }

  return NextResponse.json(
    {
      error: "preview_unavailable",
      stored_path: row.stored_path,
      note: "画面用のコピーがまだありません。Jarvis に『証憑をプレビュー用に上げて』と依頼してください。",
    },
    { status: 404 }
  );
}
