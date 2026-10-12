"""
RHK TECH Premium Permission - login + token builder.

For every account (JSON from the Netlify export function) it gets a
`new_bbs_serviceToken` from Firefox and from Chrome and writes
sessions/<name>/token.txt =  [Firefox, Chrome, Firefox, Chrome].

Per browser, in this order:
  1. reuse the token saved from the last successful login if it is still valid
  2. QR accounts:       show a QR on the website, the account owner scans it
     Password accounts: log in with ID + password; if Xiaomi asks for a
                        verification code (Gmail / SMS), the website shows a code
                        box, the user types it, and this script enters it.
  3. save the fresh tokens back to Netlify (encrypted) so the next night needs no code

Env: SITE_URL, RUNNER_SECRET (talk to Netlify), ONLY=<account name> (login mode),
     VERIFY_WAIT=900 (seconds to wait for a code / QR scan)
"""
import base64, json, os, re, sys, time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

SITE = os.environ.get("SITE_URL", "").rstrip("/")
SECRET = os.environ.get("RUNNER_SECRET", "")
ONLY = os.environ.get("ONLY", "").strip()
VERIFY_WAIT = int(os.environ.get("VERIFY_WAIT", "900"))
COOKIE_NAME = "new_bbs_serviceToken"
STATE_URL = "https://sgp-api.buy.mi.com/bbs/api/global/user/bl-switch/state"
LOGIN_URL = (
    "https://account.xiaomi.com/pass/serviceLogin?sid=18n_bbs_global&_locale=en_US"
    "&callback=https%3A%2F%2Fsgp-api.buy.mi.com%2Fbbs%2Fapi%2Fglobal%2Fuser%2Flogin-back"
    "%3Ffollowup%3Dhttps%253A%252F%252Fc.mi.com%252Fglobal"
)
H = {"x-runner-secret": SECRET, "content-type": "application/json"}


# ---------- talking to the website ----------
def say(name, state, msg="", qr=None):
    print(f"[{name}] {state}: {msg}", flush=True)
    if not SITE:
        return
    try:
        requests.post(f"{SITE}/.netlify/functions/login", headers=H, timeout=15,
                      json={"name": name, "state": state, "msg": msg, "qr": qr})
    except Exception as e:
        print(f"  (status post failed: {e})")


def wait_for_code(name, msg):
    """Show the code box on the site and wait until the user submits a code."""
    say(name, "need_code", msg)
    end = time.time() + VERIFY_WAIT
    while time.time() < end:
        time.sleep(3)
        try:
            r = requests.get(f"{SITE}/.netlify/functions/login", headers=H, timeout=15, params={"name": name})
            code = (r.json() or {}).get("code")
            if code:
                say(name, "verifying", "code received, entering it...")
                return code
        except Exception:
            pass
    raise RuntimeError("no verification code entered in time")


def token_valid(token):
    try:
        r = requests.get(STATE_URL, timeout=10,
                         headers={"Cookie": f"new_bbs_serviceToken={token};versionCode=500411;versionName=5.4.11;"})
        return r.json().get("code") != 100004
    except Exception:
        return False


# ---------- page helpers ----------
def cookie(ctx):
    for c in ctx.cookies():
        if c["name"] == COOKIE_NAME:
            return c["value"]
    return None


def page_text(page):
    try:
        return page.inner_text("body").lower()
    except Exception:
        return ""


def click_first(page, pattern):
    try:
        page.get_by_text(re.compile(pattern, re.I)).first.click(timeout=2500)
        return True
    except Exception:
        return False


def needs_code(page):
    t = page_text(page)
    return ("identity" in page.url or "authstart" in page.url.lower()
            or "verification code" in t or "verify your identity" in t)


def fill_code(page, code):
    for sel in ("input[name*='ticket']", "input[name*='code']", "input[type='tel']",
                "input[autocomplete='one-time-code']", "input[type='text']"):
        try:
            box = page.locator(sel).first
            box.fill(code, timeout=2500)
            page.keyboard.press("Enter")
            click_first(page, r"^(submit|verify|confirm|ok|next)$")
            return
        except Exception:
            continue
    raise RuntimeError("could not find the code input on the page")


# ---------- the two login methods ----------
def login_password(page, ctx, name, label, user, password):
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
    page.fill("input[name='account'], input[name='user'], #username", user)
    page.fill("input[type='password']", password)
    page.click("button[type='submit'], .btn_orange, #login-button")
    asked = False
    end = time.time() + VERIFY_WAIT
    while time.time() < end:
        time.sleep(1.5)
        tok = cookie(ctx)
        if tok:
            return tok
        t = page_text(page)
        if "captcha" in t and "verification code" not in t:
            raise RuntimeError("Xiaomi asked for a captcha (picture puzzle) - use QR login for this account")
        if needs_code(page):
            if not asked:
                click_first(page, r"e-?mail|gmail")      # prefer the email option if offered
                click_first(page, r"^(send|get)( the)? (code|verification)")
                asked = True
            code = wait_for_code(name, f"{label}: Xiaomi sent a verification code (Gmail/SMS). Type it below.")
            fill_code(page, code)
            asked = False                                  # a wrong code brings us back here
    raise RuntimeError("login did not finish in time")


def login_qr(page, ctx, name, label):
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
    click_first(page, r"qr|scan")
    shown, end = 0, time.time() + VERIFY_WAIT
    while time.time() < end:
        tok = cookie(ctx)
        if tok:
            return tok
        if time.time() - shown > 40:                      # QR codes expire, resend a fresh one
            try:
                el = page.locator("img[src*='qr' i], img[class*='qr' i], canvas").first
                png = el.screenshot(timeout=5000)
            except Exception:
                png = page.screenshot()
            say(name, "qr", f"{label}: scan this QR with the Xiaomi / Mi Community app on the phone "
                            "that is signed in to this Mi account.", "data:image/png;base64," + base64.b64encode(png).decode())
            shown = time.time()
        time.sleep(2)
    raise RuntimeError("QR was not scanned in time")


def fresh_token(pw, label, acc):
    bt = pw.firefox if label == "firefox" else pw.chromium
    kw = {} if label == "firefox" else {"channel": "chrome"}
    browser = bt.launch(headless=True, **kw)
    try:
        ctx = browser.new_context(locale="en-US", viewport={"width": 480, "height": 900})
        page = ctx.new_page()
        if acc.get("method") == "qr" or not acc.get("password"):
            return login_qr(page, ctx, acc["name"], label.capitalize())
        return login_password(page, ctx, acc["name"], label.capitalize(), acc["user"], acc["password"])
    finally:
        browser.close()


def save_tokens(name, ff, ch):
    if not SITE:
        return
    try:
        requests.post(f"{SITE}/.netlify/functions/export", headers=H, timeout=15,
                      json={"name": name, "firefox": ff, "chrome": ch})
    except Exception as e:
        print(f"[{name}] could not save tokens: {e}")


def main():
    accounts = json.load(open(sys.argv[1]))
    out_root = Path(sys.argv[2] if len(sys.argv) > 2 else "sessions")
    if ONLY:
        accounts = [a for a in accounts if a["name"] == ONLY]
    ok = 0
    with sync_playwright() as pw:
        for acc in accounts:
            name, saved = acc["name"], acc.get("tokens") or {}
            try:
                say(name, "starting", "logging in...")
                got = {}
                for label in ("firefox", "chrome"):
                    t = saved.get(label)
                    if t and token_valid(t):
                        print(f"[{name}] {label}: saved token still valid")
                        got[label] = t
                    else:
                        got[label] = fresh_token(pw, label, acc)
                save_tokens(name, got["firefox"], got["chrome"])
                d = out_root / name
                d.mkdir(parents=True, exist_ok=True)
                ff, ch = got["firefox"], got["chrome"]
                (d / "token.txt").write_text("\n".join([ff, ch, ff, ch]) + "\n")
                say(name, "ok", "Connected. Tokens saved (1,3 = Firefox, 2,4 = Chrome).")
                ok += 1
            except Exception as e:
                say(name, "failed", str(e))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
