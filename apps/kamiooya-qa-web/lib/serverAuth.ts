// サーバー側だけが持つ鍵での呼び出しかを確かめる（会員のブラウザには配らない）。
// - X-Gateway-Proof: raimo-auth（ログイン確認済みの回答ジョブ・運営画面の中継）からの呼び出し。値は RAIMO_AUTH_GATEWAY_SECRET。
// - X-Qa-Ops-Secret: Mac・GitHub Actions の運営用スクリプトからの呼び出し。値は QA_OPS_SERVER_SECRET。
// どちらも未設定・短すぎる時は通さない（鍵が無い時に開く作りにしない）。本文や URL に載せた鍵は見ない。
export type EnvGetter = (name: string) => string | undefined;

const MIN_SECRET_LENGTH = 32;

async function sha256(value: string): Promise<string> {
  const raw = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value)));
  return Array.from(raw, b => b.toString(16).padStart(2, '0')).join('');
}

/** 長さや途中までの一致で差が出にくいよう、ハッシュどうしで比べる。 */
export async function sameServerSecret(given: string, expected: string): Promise<boolean> {
  if (!given || expected.length < MIN_SECRET_LENGTH) return false;
  return (await sha256(given)) === (await sha256(expected));
}

export async function viaGateway(req: Request, env: EnvGetter): Promise<boolean> {
  return sameServerSecret((req.headers.get('x-gateway-proof') || '').trim(), (env('RAIMO_AUTH_GATEWAY_SECRET') || '').trim());
}

export async function viaOpsScript(req: Request, env: EnvGetter): Promise<boolean> {
  return sameServerSecret((req.headers.get('x-qa-ops-secret') || '').trim(), (env('QA_OPS_SERVER_SECRET') || '').trim());
}

/** raimo-auth か運営用スクリプトからの呼び出しだけ通す。 */
export async function serverAuthorized(req: Request, env: EnvGetter): Promise<boolean> {
  return (await viaGateway(req, env)) || (await viaOpsScript(req, env));
}

export const SERVER_AUTH_HEADERS = 'content-type, x-gateway-proof, x-qa-ops-secret';
