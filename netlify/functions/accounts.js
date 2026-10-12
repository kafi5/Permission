const { enc, store, isAdmin, safeName, json } = require("./_store");

exports.handler = async (event) => {
  if (!isAdmin(event)) return json(401, { error: "wrong admin password" });
  const s = store();

  if (event.httpMethod === "GET") {
    const { blobs } = await s.list();
    const out = [];
    for (const b of blobs) {
      const a = await s.get(b.key, { type: "json" });
      out.push({
        name: a.name,
        userMasked: a.userMasked,
        method: a.method || "password",
        tokensSavedAt: a.tokensSavedAt || null,
      });
    }
    return json(200, out);
  }

  if (event.httpMethod === "POST") {
    const { name, user, password, method } = JSON.parse(event.body || "{}");
    const m = method === "qr" ? "qr" : "password";
    if (!name || !user || (m === "password" && !password))
      return json(400, { error: m === "qr" ? "name and Mi ID required" : "name, user, password required" });
    const safe = safeName(name);
    const old = (await s.get(safe, { type: "json" })) || {};
    await s.setJSON(safe, {
      ...old,
      name: safe,
      method: m,
      userMasked: user.slice(0, 3) + "***" + user.slice(-2),
      user: enc(user),
      password: password ? enc(password) : null,
    });
    return json(200, { ok: true });
  }

  if (event.httpMethod === "DELETE") {
    const { name } = JSON.parse(event.body || "{}");
    await s.delete(safeName(name));
    return json(200, { ok: true });
  }
  return json(405, { error: "method" });
};
