const crypto = require("crypto");
const blobs = require("@netlify/blobs");
const { getStore } = blobs;

const key = () => crypto.createHash("sha256").update(process.env.ENCRYPTION_KEY || "").digest();

exports.enc = (text) => {
  const iv = crypto.randomBytes(12);
  const c = crypto.createCipheriv("aes-256-gcm", key(), iv);
  const data = Buffer.concat([c.update(text, "utf8"), c.final()]);
  return Buffer.concat([iv, c.getAuthTag(), data]).toString("base64");
};

exports.dec = (b64) => {
  const raw = Buffer.from(b64, "base64");
  const d = crypto.createDecipheriv("aes-256-gcm", key(), raw.subarray(0, 12));
  d.setAuthTag(raw.subarray(12, 28));
  return Buffer.concat([d.update(raw.subarray(28)), d.final()]).toString("utf8");
};

exports.store = () => getStore("rhk-accounts");
exports.loginStore = () => getStore("rhk-login");
exports.logStore = () => getStore("rhk-logs");

// Both checks fail closed: if the env var is not set, nobody gets in.
const same = (a, b) => !!b && typeof a === "string" && a.length === b.length &&
  crypto.timingSafeEqual(Buffer.from(a), Buffer.from(b));
exports.isAdmin = (e) => same(e.headers["x-admin-password"], process.env.ADMIN_PASSWORD);
exports.isRunner = (e) => same(e.headers["x-runner-secret"], process.env.RUNNER_SECRET);
exports.safeName = (n) => String(n || "").replace(/[^a-zA-Z0-9_-]/g, "").replace(/_{2,}/g, "_");
exports.json = (code, obj) => ({ statusCode: code, headers: { "content-type": "application/json" }, body: JSON.stringify(obj) });

// Every handler goes through this: connects Blobs (needed for this handler style)
// and turns any crash into a readable JSON error instead of a blank 502.
exports.wrap = (fn) => async (event) => {
  try {
    if (blobs.connectLambda) blobs.connectLambda(event);
    return await fn(event);
  } catch (e) {
    console.error(e);
    return exports.json(500, { error: "server error: " + (e && e.message ? e.message : String(e)) });
  }
};
