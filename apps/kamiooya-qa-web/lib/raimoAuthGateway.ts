// Offline repair candidate. No deployed route imports this module.
// Production requires persistent sessions, throttling and a guarded Raimo adapter.
type Member = { id: string; email: string; role: string; status: string; authVersion: string };
type Session = { uid: string; authVersion: string; expires: number };
export type GatewayDependencies = {
  origin: string;
  authenticate(email: string, password: string): Promise<Member | null>;
  member(id: string): Promise<Member | null>;
  sessions: { get(token: string): Promise<Session | null>; put(token: string, value: Session): Promise<void>; delete(token: string): Promise<void> };
  allowLogin(email: string): Promise<boolean>;
  chatOwner(id: string): Promise<string | null>;
  forward(method: string, path: string, input: Record<string, unknown>): Promise<unknown>;
  attachmentSession(uid: string, parentSession: string): Promise<unknown>;
  now?: () => number;
};
const approved = (u: Member | null): u is Member => !!u && u.status === 'approved' && ['user', 'admin', 'master_admin'].includes(u.role) && !!u.authVersion;
const publicUser = (u: Member) => ({ id: u.id, email: u.email, role: u.role, status: u.status });
// Only explicitly reviewed operations may pass; all other legacy routes stay closed.
function permission(method: string, path: string): 'member' | 'staff' | 'master' | 'chat' | 'own-list' | null {
  if (method === 'GET' && ['/comments', '/knowledge-chunks', '/knowledge-sources', '/suggested-questions'].includes(path)) return 'member';
  if (method === 'GET' && ['/admin/users', '/admin/users/pending'].includes(path)) return 'staff';
  if (method === 'PUT' && /^\/admin\/users\/[a-zA-Z0-9_-]+\/(approve|reject)$/.test(path)) return 'master';
  if (method === 'POST' && path === '/chat-sessions') return 'member';
  if (method === 'GET' && /^\/users\/[a-zA-Z0-9_-]+\/chat-sessions$/.test(path)) return 'own-list';
  if ((method === 'GET' && /^\/chat-sessions\/[a-zA-Z0-9_-]+$/.test(path)) ||
      (method === 'PUT' && /^\/chat-sessions\/[a-zA-Z0-9_-]+\/touch$/.test(path)) ||
      (method === 'POST' && /^\/chat-sessions\/[a-zA-Z0-9_-]+\/messages(?:-append|-fast|-semantic|-semantic-fast)?$/.test(path))) return 'chat';
  return null;
}
// Deny-by-default user projection rather than recursive deletion of a few field names.
function safeUsers(result: unknown): unknown {
  const safe = (u: any) => ({ id: u.id, email: u.email, role: u.role, status: u.status });
  const r = result as any;
  if (!r || !Array.isArray(r.users)) throw new Error('invalid_users_response');
  return { users: r.users.map(safe) };
}
export function createRaimoAuthGateway(d: GatewayDependencies) {
  const now = d.now || Date.now;
  return async (req: Request): Promise<Response> => {
    const origin = req.headers.get('origin');
    const headers = { 'Content-Type': 'application/json', 'Cache-Control': 'no-store', 'Vary': 'Origin',
      ...(origin === d.origin ? { 'Access-Control-Allow-Origin': d.origin, 'Access-Control-Allow-Headers': 'authorization, content-type', 'Access-Control-Allow-Methods': 'GET, POST, PUT, OPTIONS' } : {}) };
    const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers });
    if (origin && origin !== d.origin) return json({ error: 'forbidden_origin' }, 403);
    if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers });
    try {
      const url = new URL(req.url), path = url.pathname;
      // Keep paths canonical; no query-based credentials, actors or alternate route syntax.
      if (url.search || /%|\/\//.test(path)) return json({ error: 'invalid_request' }, 400);
      const text = await req.text();
      if (text.length > 65536) return json({ error: 'request_too_large' }, 413);
      let input: Record<string, unknown> = {};
      if (text) {
        try { input = JSON.parse(text); } catch { return json({ error: 'invalid_request' }, 400); }
        if (!input || typeof input !== 'object' || Array.isArray(input)) return json({ error: 'invalid_request' }, 400);
      }
      if (req.method === 'POST' && path === '/auth/login') {
        const email = String(input.email || '').trim().toLowerCase();
        const password = String(input.password_hash || '');
        if (!email || !password || email.length > 320 || password.length > 1024) return json({ error: 'invalid_credentials' }, 401);
        if (!await d.allowLogin(email)) return json({ error: 'try_later' }, 429);
        const user = await d.authenticate(email, password);
        if (!approved(user)) return json({ error: 'invalid_credentials' }, 401);
        const token = Array.from(crypto.getRandomValues(new Uint8Array(32)), b => b.toString(16).padStart(2, '0')).join('');
        await d.sessions.put(token, { uid: user.id, authVersion: user.authVersion, expires: now() + 900000 });
        return json({ user: publicUser(user), auth_token: token, expires_in: 900 });
      }
      const authorization = req.headers.get('authorization') || '';
      const token = /^Bearer ([0-9a-f]{64})$/.exec(authorization)?.[1];
      const session = token ? await d.sessions.get(token) : null;
      if (!session || session.expires <= now()) return json({ error: 'login_required' }, 401);
      if (path === '/auth/logout' && req.method === 'POST') {
        await d.sessions.delete(token!); return json({ ok: true });
      }
      const user = await d.member(session.uid);
      if (!approved(user) || user.id !== session.uid || user.authVersion !== session.authVersion) return json({ error: 'membership_required' }, 403);
      if (path === '/auth/attachment-session' && req.method === 'POST') {
        // Identity comes solely from the verified session; input password/user/role ignored.
        const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(token!)));
        const parentSession = Array.from(digest, b => b.toString(16).padStart(2, '0')).join('');
        return json(await d.attachmentSession(user.id, parentSession));
      }
      const level = permission(req.method, path);
      if (!level) return json({ error: 'route_not_reviewed' }, 403);
      if ((level === 'staff' && !['admin', 'master_admin'].includes(user.role)) ||
          (level === 'master' && user.role !== 'master_admin')) return json({ error: 'forbidden' }, 403);
      if (level === 'own-list' && path.split('/')[2] !== user.id) return json({ error: 'forbidden' }, 403);
      if (level === 'chat' && await d.chatOwner(path.split('/')[2]) !== user.id) return json({ error: 'forbidden' }, 403);
      // Never forward browser-supplied credentials, internal secrets or actor identity.
      const forwarded = { ...input };
      for (const key of ['actor_user_id', 'user_id', 'role', 'status', 'secret', '__gateway_secret', 'password_hash', 'auth_token']) delete forwarded[key];
      forwarded.actor_user_id = user.id;
      if (path === '/chat-sessions') forwarded.user_id = user.id;
      const result = await d.forward(req.method, path, forwarded);
      return json(level === 'staff' ? safeUsers(result) : result);
    } catch {
      // Neither upstream response bodies nor credential/session values are exposed.
      return json({ error: 'service_unavailable' }, 503);
    }
  };
}
