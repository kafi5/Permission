// Live script output per session / token.
// runner POST {name, token, lines:[...], reset?}  -> append lines (key = <name>__t<token>)
// admin  GET  ?name=<session>                     -> {tokens:{"1":{lines,at},...}}
// admin  GET  (no name)                           -> {sessions:[{name,at}]}
// admin  DELETE ?name=<session>                   -> clear that session's output
const { logStore, isAdmin, isRunner, safeName, json, wrap } = require("./_store");

const MAX_STORED = 300, MAX_SENT = 200, MAX_LINE = 300;

exports.handler = wrap(async (event) => {
  const runner = isRunner(event);
  if (!runner && !isAdmin(event)) return json(401, { error: "unauthorized" });
  const s = logStore();
  const q = event.queryStringParameters || {};

  if (event.httpMethod === "POST") {
    if (!runner) return json(401, { error: "runner only" });
    const b = JSON.parse(event.body || "{}");
    const name = safeName(b.name), tok = parseInt(b.token, 10);
    if (!name || !(tok >= 1 && tok <= 99)) return json(400, { error: "name and token required" });
    const key = `${name}__t${tok}`;
    const cur = b.reset ? null : await s.get(key, { type: "json" });
    const lines = ((cur && cur.lines) || []).concat((b.lines || []).map((l) => String(l).slice(0, MAX_LINE)));
    const sent = ((cur && cur.sent) || 0) + (parseInt(b.sent, 10) || 0);
    const recv = ((cur && cur.recv) || 0) + (parseInt(b.recv, 10) || 0);
    await s.setJSON(key, { lines: lines.slice(-MAX_STORED), at: Date.now(), sent, recv });
    return json(200, { ok: true });
  }

  if (runner) return json(403, { error: "admin only" });

  const { blobs } = await s.list();
  const keys = blobs.map((b) => b.key);

  if (event.httpMethod === "DELETE") {
    const name = safeName(q.name);
    for (const k of keys) if (k.startsWith(name + "__t")) await s.delete(k);
    return json(200, { ok: true });
  }

  if (event.httpMethod === "GET") {
    const name = safeName(q.name);
    if (!name) {
      const seen = {};
      for (const k of keys) {
        const n = k.split("__t")[0];
        const v = await s.get(k, { type: "json" });
        seen[n] = Math.max(seen[n] || 0, (v && v.at) || 0);
      }
      return json(200, { sessions: Object.entries(seen).map(([n, at]) => ({ name: n, at })) });
    }
    const tokens = {};
    for (const k of keys.filter((k) => k.startsWith(name + "__t"))) {
      const v = await s.get(k, { type: "json" });
      if (v) tokens[k.split("__t")[1]] = { lines: v.lines.slice(-MAX_SENT), at: v.at, sent: v.sent || 0, recv: v.recv || 0 };
    }
    return json(200, { tokens });
  }
  return json(405, { error: "method" });
});
