import bcrypt from "bcryptjs";
import { createHash } from "node:crypto";

function isBcryptHash(s: string) {
  return /^\$2[aby]\$\d{2}\$/.test(s);
}

function isSha256Hex(s: string) {
  return /^[a-f0-9]{64}$/i.test(s);
}

export async function hashPasswordForStorage(password: string): Promise<string> {
  // 既存移行データとの互換より安全性を優先し、今後はbcryptで保存する
  const salt = await bcrypt.genSalt(12);
  return await bcrypt.hash(password, salt);
}

export async function verifyPassword(passwordInput: string, storedPasswordHash: string): Promise<boolean> {
  const stored = String(storedPasswordHash ?? "");
  const input = String(passwordInput ?? "");

  // 互換: 旧データが平文保存だった場合
  if (stored === input) return true;

  // 互換: 旧データがsha256(hex)だった場合（どの旧実装でもよくある）
  if (isSha256Hex(stored)) {
    const sha = createHash("sha256").update(input, "utf8").digest("hex");
    if (sha.toLowerCase() === stored.toLowerCase()) return true;
  }

  // 推奨: bcrypt
  if (isBcryptHash(stored)) {
    return await bcrypt.compare(input, stored);
  }

  return false;
}

