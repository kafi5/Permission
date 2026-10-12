// Called only by the GitHub Action (needs RUNNER_SECRET).
// GET  -> accounts with decrypted credentials + saved browser tokens
// POST -> save the tokens a login produced: {name, firefox, chrome}
const { enc, dec, store, isRunner, safeName, json } = require("./_store");

exports.handler = async (event) => {
  if (!isRunner(event)) return json(401, { error: "no" });
  const s = store();

  if (event.httpMethod === "POST") {
    const { name, firefox, chrome } = JSON.parse(event.body || "{}");
    const key = safeName(name);
    const a = await s.get(key, { type: "json" });
    if (!a) return json(404, { error: "unknown account" });
    a.tokens = enc(JSON.stringify({ firefox, chrome }));
    a.tokensSavedAt = new Date().toISOString();
    await s.setJSON(key, a);
    return json(200, { ok: true });
  }

  const { blobs } = await s.list();
  const out = [];
  for (const b of blobs) {
    const a = await s.get(b.key, { type: "json" });
    out.push({
      name: a.name,
      method: a.method || "password",
      user: dec(a.user),
      password: a.password ? dec(a.password) : null,
      tokens: a.tokens ? JSON.parse(dec(a.tokens)) : null,
    });
  }
  return json(200, out);
};
