// Live login conversation between the GitHub runner and the website.
//
// runner POST {name, state, msg?, qr?}  -> publish what the login is waiting for
//   state: starting | need_code | qr | verifying | ok | failed
// runner GET  ?name=                    -> poll for the code the user typed
// admin  GET  ?name=                    -> status for the website (no code returned)
// admin  POST {name, code}              -> user submits the verification code
// admin  POST {name, reset:true}        -> clear status
const { loginStore, isAdmin, isRunner, safeName, json } = require("./_store");

exports.handler = async (event) => {
  const runner = isRunner(event);
  if (!runner && !isAdmin(event)) return json(401, { error: "unauthorized" });
  const s = loginStore();

  if (event.httpMethod === "GET") {
    const name = safeName((event.queryStringParameters || {}).name);
    if (!name) return json(400, { error: "name required" });
    const st = (await s.get(name, { type: "json" })) || { state: "idle" };
    if (runner) return json(200, { code: st.code || null });
    const { code, ...pub } = st;
    return json(200, { ...pub, codeSent: !!code });
  }

  if (event.httpMethod === "POST") {
    const b = JSON.parse(event.body || "{}");
    const name = safeName(b.name);
    if (!name) return json(400, { error: "name required" });
    let st = (await s.get(name, { type: "json" })) || { state: "idle" };

    if (runner) {
      if (b.state !== st.state || b.state === "need_code") delete st.code; // fresh prompt, old code is stale
      st = { ...st, state: b.state, msg: b.msg || "", qr: b.qr || null, at: Date.now() };
      if (b.state === "verifying" || b.state === "ok" || b.state === "failed") delete st.code;
    } else if (b.reset) {
      st = { state: "idle" };
    } else if (b.code) {
      st.code = String(b.code).trim().slice(0, 12);
      st.at = Date.now();
    }
    await s.setJSON(name, st);
    return json(200, { ok: true });
  }
  return json(405, { error: "method" });
};
