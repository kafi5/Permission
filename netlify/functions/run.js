const { isAdmin, safeName, json, wrap } = require("./_store");

// body: {now:true}                 -> tonight's cycle, applying immediately (test)
//       {}                         -> tonight's cycle now (waits for 9:55 PM)
//       {mode:"login", name:"x"}   -> only connect that account (Gmail code / QR), no apply
exports.handler = wrap(async (event) => {
  if (!isAdmin(event)) return json(401, { error: "wrong admin password" });
  const { now, mode, name } = JSON.parse(event.body || "{}");
  const inputs = { now: now ? "true" : "false", mode: mode === "login" ? "login" : "nightly", name: safeName(name) };
  const r = await fetch(
    `https://api.github.com/repos/${process.env.GH_REPO}/actions/workflows/premium-permission.yml/dispatches`,
    {
      method: "POST",
      headers: { authorization: `Bearer ${process.env.GH_TOKEN}`, accept: "application/vnd.github+json" },
      body: JSON.stringify({ ref: "main", inputs }),
    }
  );
  return json(r.ok ? 200 : 500, { ok: r.ok, status: r.status });
});
