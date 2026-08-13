export function guessMime(name: string | null | undefined): string {
  const n = (name || "").toLowerCase();
  if (n.endsWith(".pdf")) return "application/pdf";
  if (n.endsWith(".png")) return "image/png";
  if (n.endsWith(".jpg") || n.endsWith(".jpeg")) return "image/jpeg";
  if (n.endsWith(".gif")) return "image/gif";
  if (n.endsWith(".webp")) return "image/webp";
  if (n.endsWith(".txt") || n.endsWith(".csv") || n.endsWith(".md")) {
    return "text/plain; charset=utf-8";
  }
  return "application/octet-stream";
}

export function previewKind(
  name: string | null | undefined
): "pdf" | "image" | "text" | "other" {
  const mime = guessMime(name);
  if (mime === "application/pdf") return "pdf";
  if (mime.startsWith("image/")) return "image";
  if (mime.startsWith("text/")) return "text";
  return "other";
}
