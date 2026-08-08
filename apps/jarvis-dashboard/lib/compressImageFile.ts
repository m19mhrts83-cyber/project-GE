/** ブラウザで画像を縮小して Server Action の本文制限を避ける */

export async function compressImageFile(
  file: File,
  opts?: { maxEdge?: number; quality?: number },
): Promise<File> {
  const maxEdge = opts?.maxEdge ?? 1600;
  const quality = opts?.quality ?? 0.82;

  if (!file.type.startsWith("image/")) return file;
  // すでに小さいならそのまま
  if (file.size <= 700_000) return file;

  const bitmap = await createImageBitmap(file);
  try {
    const scale = Math.min(1, maxEdge / Math.max(bitmap.width, bitmap.height));
    const w = Math.max(1, Math.round(bitmap.width * scale));
    const h = Math.max(1, Math.round(bitmap.height * scale));
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    if (!ctx) return file;
    ctx.drawImage(bitmap, 0, 0, w, h);

    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", quality),
    );
    if (!blob || blob.size >= file.size) return file;

    const base = file.name.replace(/\.[^.]+$/, "") || "snore";
    return new File([blob], `${base}.jpg`, {
      type: "image/jpeg",
      lastModified: Date.now(),
    });
  } finally {
    bitmap.close();
  }
}

export async function compressImageFiles(files: File[]): Promise<File[]> {
  const out: File[] = [];
  for (const f of files) {
    try {
      out.push(await compressImageFile(f));
    } catch {
      out.push(f);
    }
  }
  return out;
}
