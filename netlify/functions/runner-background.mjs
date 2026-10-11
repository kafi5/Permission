// Background function (up to 15 min). Does what old.py does, for every enabled account.
import { getStore } from "@netlify/blobs";
import { checkState, applyOnce, deviceId, interpretState, interpretApply } from "../lib/xiaomi.mjs";

const WINDOW_MS = 10_000; // how long to keep sending after midnight
const GAP_MS = 150; // pause between requests
const MAX_WAIT_MS = 14 * 60_000; // Netlify background limit is 15 min

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const bj = (t) => new Date(t + 8 * 3600e3).toISOString().replace("T", " ").replace("Z", "") + " (UTC+8)";

function targetFor(offset) {
  const d = new Date();
  let mid = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), 16, 0, 0); // 00:00 Beijing
  if (Date.now() > mid + 30_000) mid += 86_400_000;
  return mid - offset;
}

async function runAccount(acc, store) {
  const lines = [];
  const log = (m) => lines.push(`[${bj(Date.now())}] ${m}`);
  const flush = () =>
    store.setJSON(`log-${acc.id}`, { id: acc.id, label: acc.label, updated: Date.now(), lines });
  const dev = deviceId();
  try {
    log("Checking account status");
    const st = interpretState(await checkState(acc.token, dev));
    log(`[Account status] ${st.line}`);
    if (!st.proceed && !(st.askable && acc.force)) {
      log("Skipped.");
      return await flush();
    }

    const offset = Number(acc.offset) || 0;
    const target = targetFor(offset);
    log(`[Offset set] ${offset.toFixed(2)} ms`);
    log(`[Waiting until] ${bj(target)}`);
    if (target - Date.now() > MAX_WAIT_MS) {
      log("Target is too far away (missed the window). Skipped.");
      return await flush();
    }
    await flush();

    // wait, re-warm the connection ~3s before, then spin for the last few ms
    await sleep(Math.max(0, target - Date.now() - 3000));
    await checkState(acc.token, dev).catch(() => {});
    const left = target - Date.now();
    if (left > 50) await sleep(left - 50);
    while (Date.now() < target) {}

    log(`Time reached. Sending requests...`);
    const end = Date.now() + WINDOW_MS;
    while (Date.now() < end) {
      log(`[Request] Sending at ${bj(Date.now())}`);
      let res;
      try {
        res = await applyOnce(acc.token, dev);
      } catch (e) {
        log(`[Network error] ${e.message}`);
        await sleep(GAP_MS);
        continue;
      }
      log(`[Response] ${bj(Date.now())} ${JSON.stringify(res)}`);
      const r = interpretApply(res);
      log(`[Status] ${r.line}`);
      if (r.done) {
        if (r.recheck) {
          const s = interpretState(await checkState(acc.token, dev));
          log(`[Account status] ${s.line}`);
        }
        break;
      }
      await sleep(GAP_MS);
    }
    log("Done.");
  } catch (e) {
    log(`[Error] ${e.message}`);
  }
  await flush();
}

export default async (req) => {
  if (req.headers.get("x-cron-secret") !== (process.env.ADMIN_PASSWORD || "\0")) return;
  const store = getStore("xiaomi");
  const all = (await store.get("accounts", { type: "json" })) || [];
  const seen = new Set();
  const accounts = all.filter((a) => a.enabled && a.token && !seen.has(a.token) && seen.add(a.token));
  await Promise.all(accounts.map((a) => runAccount(a, store)));
};
