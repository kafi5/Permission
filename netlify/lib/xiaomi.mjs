import { createHash } from "node:crypto";

const BASE = "https://sgp-api.buy.mi.com/bbs/api/global";

export const deviceId = () =>
  createHash("sha1").update(`${Math.random()}-${Date.now()}`).digest("hex").toUpperCase();

const cookie = (token, dev) =>
  `new_bbs_serviceToken=${token};versionCode=500411;versionName=5.4.11;deviceId=${dev};`;

async function parse(r) {
  const text = await r.text();
  try { return JSON.parse(text); } catch { return { raw: text }; }
}

// GET bl-switch/state (same as check_unlock_status in old.py)
export async function checkState(token, dev) {
  const r = await fetch(`${BASE}/user/bl-switch/state`, {
    headers: { Cookie: cookie(token, dev), "Content-Type": "application/json; charset=utf-8" },
  });
  return parse(r);
}

// POST apply/bl-auth (same body/headers as old.py)
export async function applyOnce(token, dev) {
  const r = await fetch(`${BASE}/apply/bl-auth`, {
    method: "POST",
    headers: {
      Cookie: cookie(token, dev),
      "Content-Type": "application/json; charset=utf-8",
      "User-Agent": "okhttp/4.12.0",
      Connection: "keep-alive",
    },
    body: '{"is_retry":true}',
  });
  return parse(r);
}

export function interpretState(res) {
  if (res?.code === 100004)
    return { proceed: false, line: "Cookie expired, token update korte hobe." };
  const d = res?.data || {};
  const { is_pass, button_state, deadline_format = "" } = d;
  if (is_pass === 4) {
    if (button_state === 1) return { proceed: true, line: "Request can be sent." };
    if (button_state === 2)
      return { proceed: false, askable: true, line: `Locked for requests until ${deadline_format} (Month/Day).` };
    if (button_state === 3)
      return { proceed: false, askable: true, line: "Account created less than 30 days ago." };
  }
  if (is_pass === 1)
    return { proceed: false, line: `Request already approved, unlock possible until ${deadline_format}.` };
  return { proceed: false, line: "Unknown state." };
}

export function interpretApply(res) {
  const code = res?.code;
  const d = res?.data || {};
  if (code === 0) {
    if (d.apply_result === 1) return { done: true, recheck: true, line: "Request approved, checking status..." };
    if (d.apply_result === 3)
      return { done: true, line: `Limit reached. Try again on ${d.deadline_format || "Not specified"} (Month/Day).` };
    if (d.apply_result === 4)
      return { done: true, line: `Blocked until ${d.deadline_format || "Not specified"} (Month/Day).` };
    return { done: false, line: `code 0, apply_result ${d.apply_result}` };
  }
  if (code === 100001) return { done: false, line: "Request denied, error in request." };
  if (code === 100003) return { done: true, recheck: true, line: "Request may be approved, checking status..." };
  if (code === 100004) return { done: true, line: "Cookie expired." };
  if (code !== undefined) return { done: false, line: `Unknown request state: ${code}` };
  return { done: false, line: "Response missing required code." };
}
