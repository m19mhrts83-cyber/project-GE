import bcrypt from "bcryptjs";
import { createHash } from "node:crypto";

function isBcryptHash(s: string) {
  return /^\$2[aby]\$\d{2}\$/.test(s);
}

function isSha256Hex(s: string) {
  return /^[a-f0-9]{64}$/i.test(s);
}

export async function verifyPassword(passwordInput: string, storedPasswordHash: string): Promise<boolean> {
  const stored = String(storedPasswordHash ?? "");
  const input = String(passwordInput ?? "");
  if (stored === input) return true;
  if (isSha256Hex(stored)) {
    const sha = createHash("sha256").update(input, "utf8").digest("hex");
    if (sha.toLowerCase() === stored.toLowerCase()) return true;
  }
  if (isBcryptHash(stored)) {
    return await bcrypt.compare(input, stored);
  }
  return false;
}
