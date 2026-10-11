import { getStore } from "@netlify/blobs";
import { checkState, deviceId, interpretState } from "../lib/xiaomi.mjs";

const json = (o, status = 200) =>
  new Response(JSON.stringify(o), { status, headers: { "content-type": "application/json" } });

export default async (req) => {
  const pw = process.env.ADMIN_PASSWORD;
  if (!pw || req.headers.get("x-admin-password") !== pw) return json({ error: "unauthorized" }, 401);

  const store = getStore("xiaomi");
  const path = new URL(req.url).pathname.replace(/^\/api\/?/, "");

  if (path === "accounts" && req.method === "GET")
    return json((await store.get("accounts", { type: "json" })) || []);

  if (path === "accounts" && req.method === "PUT") {
    const list = await req.json();
    if (!Array.isArray(list)) return json({ error: "bad body" }, 400);
    const clean = list
      .map((a) => ({
        id: a.id || crypto.randomUUID(),
        label: String(a.label || "").slice(0, 60),
        token: String(a.token || "").trim(),
        offset: Number(a.offset) || 0,
        enabled: a.enabled !== false,
        force: !!a.force,
      }))
      .filter((a) => a.token);
    await store.setJSON("accounts", clean);
    return json({ ok: true, saved: clean.length, accounts: clean });
  }

  if (path === "status" && req.method === "POST") {
    const { token } = await req.json();
    if (!token) return json({ error: "token missing" }, 400);
    const raw = await checkState(String(token).trim(), deviceId());
    return json({ ...interpretState(raw), raw });
  }

  if (path === "logs" && req.method === "GET") {
    const { blobs } = await store.list({ prefix: "log-" });
    const out = [];
    for (const b of blobs) out.push(await store.get(b.key, { type: "json" }));
    return json(out.filter(Boolean));
  }

  return json({ error: "not found" }, 404);
};

export const config = { path: "/api/*" };
