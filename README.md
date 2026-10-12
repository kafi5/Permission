# RHK Tech Premium Permission

Netlify site (`public/` + `netlify/functions/`) + GitHub Actions (`.github/workflows/premium-permission.yml`).

## Flow
1. Website: add Mi ID + password (stored AES-256-GCM encrypted in Netlify Blobs).
2. 9:30 PM BD (cron 15:30 UTC): the Action fetches accounts, logs in on **Firefox** and **Chrome** (Playwright), reads `new_bbs_serviceToken` from each.
3. `token.txt` per account = `[Firefox, Chrome, Firefox, Chrome]` (tokens 1,3 = Firefox; 2,4 = Chrome).
4. Waits until 9:55:00 PM BD (15:55 UTC), then runs `old.py` 4x in parallel per account.
5. Tokens and accounts.json are deleted after the run.

## Gmail / SMS code and QR login
- Add an account as **Password** (code box appears if Xiaomi sends a Gmail/SMS code) or **QR** (account owner scans a QR shown on the site, no password stored).
- Press **Connect** on the account. GitHub starts a login-only run, the site shows the code box or QR, and the tokens are saved (encrypted) when it finishes.
- Firefox and Chrome are two separate logins, so expect up to two codes / scans per account.
- Nightly run reuses saved tokens while they are valid; it only waits ~7 minutes for a code, so it never misses 9:55 PM.

## Live output
The site's **Live output** card shows, per session, what each of the 4 tokens prints (Firefox/Chrome labels), refreshing every 3 seconds. Output is sent by `scripts/ship_logs.py`; the last ~300 lines per token are kept and replaced at the next run.

## Many sessions
Every account is a session and all sessions start together. No limit in the code; a GitHub runner has 2 CPU / 7 GB, so ~40 sessions (160 processes) is a sensible ceiling per run.

## Setup
Put your existing `old.py` (and `timeshift.txt`) in the repo root. Check how it reads its token
(the workflow passes `TOKEN_FILE=tN.txt`; adjust the loop if your script reads `token.txt` directly).

Netlify env vars: `ADMIN_PASSWORD`, `ENCRYPTION_KEY` (long random string), `RUNNER_SECRET`, `GH_TOKEN` (PAT with workflow scope), `GH_REPO` (owner/repo).
GitHub repo secrets: `RUNNER_SECRET` (same value), `SITE_URL` (https://yoursite.netlify.app).

## Known limits
- Xiaomi may ask for captcha / 2-step verification on fresh datacenter IPs (GitHub). Those accounts are skipped and logged as FAILED.
- GitHub cron can start late, which is why login starts 25 min early.
- Login URL/selectors in `scripts/login_tokens.py` are untested against live Xiaomi - run once with "Apply immediately" to verify.
