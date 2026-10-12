"""
RHK TECH Premium Permission - old.py (headless version of a.py, RHK_TECH_v070425)

Usage (run inside a session folder that has token.txt and timeshift.txt):
    python old.py <token_line_number>
    TOKEN_NUMBER=2 python old.py

What it does (same logic as a.py, but no prompts so GitHub Actions can run it):
  1. checks the account status with the token on line N of token.txt
  2. waits for Beijing midnight (00:00 CST = 10:00 PM Bangladesh), minus the
     offset (ms) on line N of timeshift.txt
  3. sends the apply request in a loop until approved / limit reached /
     the run window closes (00:05 CST = 10:05 PM Bangladesh)

Env options:
  APPLY_NOW=1          skip the wait and start sending immediately (test run)
  CONTINUE_LOCKED=0    stop instead of trying when the account is locked / <30 days
  WINDOW_MINUTES=5     how long after midnight to keep sending (default 5)
  REQUEST_GAP_MS=0     small sleep between requests (default 0 = as fast as possible)

Exit codes: 0 approved / already approved, 1 error, 2 not eligible, 3 limit reached / blocked,
            4 window closed without approval
"""
import hashlib
import json
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone

import ntplib
import pytz
import urllib3

try:
    from colorama import Fore, Style, init as _cinit
    _cinit(autoreset=True)
    G, Y, R, X = Fore.GREEN, Fore.YELLOW, Fore.RED, Fore.RESET
    YB = Style.BRIGHT + Fore.YELLOW
except ImportError:  # colours are optional
    G = Y = R = X = YB = ""

SCRIPT_VERSION = "RHK_TECH_v070425"
NTP_SERVERS = [
    "ntp0.ntp-servers.net", "ntp1.ntp-servers.net", "ntp2.ntp-servers.net",
    "ntp3.ntp-servers.net", "ntp4.ntp-servers.net", "ntp5.ntp-servers.net",
    "ntp6.ntp-servers.net", "time.google.com", "pool.ntp.org",
]
BASE = "https://sgp-api.buy.mi.com/bbs/api/global"
BEIJING = pytz.timezone("Asia/Shanghai")

TOKEN_NUMBER = 0
TAG = ""


def log(color, label, msg=""):
    print(f"{TAG}{color}[{label}]: {X}{msg}", flush=True)


def read_line(path, n):
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    if n < 1 or n > len(lines):
        raise ValueError(f"{path} has no line {n}")
    return lines[n - 1].strip()


def generate_device_id():
    raw = f"{random.random()}-{time.time()}"
    return hashlib.sha1(raw.encode()).hexdigest().upper()


def get_initial_beijing_time():
    client = ntplib.NTPClient()
    for server in NTP_SERVERS:
        try:
            resp = client.request(server, version=3, timeout=3)
            t = datetime.fromtimestamp(resp.tx_time, timezone.utc).astimezone(BEIJING)
            log(G, "Beijing time", t.strftime("%Y-%m-%d %H:%M:%S.%f") + f"  (NTP {server})")
            return t
        except Exception as e:
            print(f"{TAG}NTP {server} failed: {e}", flush=True)
    log(R, "Warning", "no NTP server reachable - using system clock")
    return datetime.now(timezone.utc).astimezone(BEIJING)


def beijing_now(start_bj, start_ts):
    return start_bj + timedelta(seconds=time.time() - start_ts)


class Session:
    def __init__(self):
        self.http = urllib3.PoolManager(
            maxsize=10, retries=True,
            timeout=urllib3.Timeout(connect=2.0, read=15.0),
        )

    def request(self, method, url, headers=None, body=None):
        try:
            h = dict(headers or {})
            h["Content-Type"] = "application/json; charset=utf-8"
            if method == "POST":
                if body is None:
                    body = b'{"is_retry":true}'
                h["Content-Length"] = str(len(body))
                h["Accept-Encoding"] = "gzip, deflate, br"
                h["User-Agent"] = "okhttp/4.12.0"
                h["Connection"] = "keep-alive"
            return self.http.request(method, url, headers=h, body=body, preload_content=False)
        except Exception as e:
            print(f"{TAG}[Network error] {e}", flush=True)
            return None


def cookie_header(token, device_id):
    return {"Cookie": f"new_bbs_serviceToken={token};versionCode=500411;versionName=5.4.11;deviceId={device_id};"}


def check_status(sess, token, device_id):
    """Returns True if we should go on and apply. Exits the process otherwise."""
    resp = sess.request("GET", f"{BASE}/user/bl-switch/state", cookie_header(token, device_id))
    if resp is None:
        log(R, "Error", "could not read account status")
        sys.exit(1)
    try:
        body = json.loads(resp.data.decode("utf-8"))
    finally:
        resp.release_conn()

    if body.get("code") == 100004:
        log(R, "Error", "token expired / invalid")
        sys.exit(1)

    data = body.get("data") or {}
    is_pass, button, deadline = data.get("is_pass"), data.get("button_state"), data.get("deadline_format", "")
    keep_going = os.environ.get("CONTINUE_LOCKED", "1") != "0"

    if is_pass == 4:
        if button == 1:
            log(G, "Account status", "request can be sent")
            return True
        if button == 2:
            log(G, "Account status", f"locked for requests until {deadline} (Month/Day)")
        elif button == 3:
            log(G, "Account status", "account created less than 30 days ago")
        else:
            log(G, "Account status", f"unknown button_state {button}")
        if keep_going:
            log(Y, "Continue", "trying anyway (CONTINUE_LOCKED=1)")
            return True
        sys.exit(2)
    if is_pass == 1:
        log(G, "Account status", f"already approved, unlock possible until {deadline}")
        sys.exit(0)
    log(G, "Account status", f"unknown state: {body}")
    sys.exit(2)


def window_minutes():
    return float(os.environ.get("WINDOW_MINUTES", "5"))


def compute_target(now_bj, offset_s):
    """Beijing midnight to fire at. If we start inside the run window, fire now."""
    today_mid = now_bj.replace(hour=0, minute=0, second=0, microsecond=0)
    window_end = today_mid + timedelta(minutes=window_minutes())
    if today_mid - timedelta(seconds=offset_s) <= now_bj < window_end:
        return now_bj, window_end                      # already in the window
    target = today_mid + timedelta(days=1)
    return target - timedelta(seconds=offset_s), target + timedelta(minutes=window_minutes())


def wait_until(start_bj, start_ts, target):
    log(G, "Waiting until", target.strftime("%Y-%m-%d %H:%M:%S.%f") + " (UTC+8)")
    while True:
        diff = (target - beijing_now(start_bj, start_ts)).total_seconds()
        if diff <= 0:
            return
        time.sleep(min(1.0, diff - 1) if diff > 1 else 0.0001)


def apply_loop(sess, token, device_id, start_bj, start_ts, window_end):
    url = f"{BASE}/apply/bl-auth"
    hdr = cookie_header(token, device_id)
    gap = float(os.environ.get("REQUEST_GAP_MS", "0")) / 1000
    sent = 0
    while beijing_now(start_bj, start_ts) < window_end:
        t0 = beijing_now(start_bj, start_ts)
        resp = sess.request("POST", url, hdr)
        sent += 1
        if resp is None:
            continue
        t1 = beijing_now(start_bj, start_ts)
        try:
            raw = resp.data
            resp.release_conn()
            js = json.loads(raw.decode("utf-8"))
        except Exception as e:
            log(R, "Error", f"bad response: {e}")
            continue
        code, data = js.get("code"), js.get("data") or {}
        stamp = f"{t0.strftime('%H:%M:%S.%f')[:-3]} -> {t1.strftime('%H:%M:%S.%f')[:-3]}"
        if code == 0:
            res = data.get("apply_result")
            if res == 1:
                log(G, "Status", f"APPROVED ({stamp})")
                check_status(sess, token, device_id)
                return 0
            if res in (3, 4):
                log(G, "Status", f"limit reached / blocked, next: {data.get('deadline_format', '?')} ({stamp})")
                return 3
            log(G, "Status", f"apply_result={res} ({stamp})")
        elif code == 100003:
            log(G, "Status", f"may be approved ({stamp}) {js}")
            check_status(sess, token, device_id)
            return 0
        else:
            log(Y, "Status", f"code={code} ({stamp}) {js}")
        if gap:
            time.sleep(gap)
    log(Y, "Done", f"window closed, {sent} requests sent")
    return 4


def main():
    global TOKEN_NUMBER, TAG
    arg = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("TOKEN_NUMBER")
    if not arg or not arg.isdigit():
        print("usage: python old.py <token_line_number>")
        sys.exit(1)
    TOKEN_NUMBER = int(arg)
    TAG = f"[T{TOKEN_NUMBER}] "

    print(f"{YB}{SCRIPT_VERSION}_token_#{TOKEN_NUMBER}{X}", flush=True)
    try:
        token = read_line("token.txt", TOKEN_NUMBER)
        offset_ms = float(read_line("timeshift.txt", TOKEN_NUMBER))
    except Exception as e:
        log(R, "Error", e)
        sys.exit(1)
    if not token:
        log(R, "Error", f"token line {TOKEN_NUMBER} is empty")
        sys.exit(1)

    device_id = generate_device_id()
    sess = Session()
    check_status(sess, token, device_id)

    start_bj = get_initial_beijing_time()
    start_ts = time.time()
    log(G, "Offset set", f"{offset_ms:.2f} ms")

    if os.environ.get("APPLY_NOW") == "1":
        window_end = start_bj + timedelta(minutes=window_minutes())
        log(Y, "APPLY_NOW", "skipping the wait")
    else:
        target, window_end = compute_target(start_bj, offset_ms / 1000)
        if target > start_bj:
            wait_until(start_bj, start_ts, target)
        log(G, "Time reached", "sending requests...")

    sys.exit(apply_loop(sess, token, device_id, start_bj, start_ts, window_end))


if __name__ == "__main__":
    main()
