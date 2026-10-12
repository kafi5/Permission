"""
Pipe a process into this to show its output on the website too:

    python -u old.py 1 2>&1 | python scripts/ship_logs.py <session-name> 1

Every line is echoed to stdout (so it is still in the GitHub log) and sent to Netlify
in small batches. It never fails the run if the website is unreachable.
"""
import os, re, sys, threading, time

import requests

name, tok = sys.argv[1], int(sys.argv[2])
SITE = os.environ.get("SITE_URL", "").rstrip("/")
H = {"x-runner-secret": os.environ.get("RUNNER_SECRET", ""), "content-type": "application/json"}
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

buf, lock, first, done = [], threading.Lock(), [True], threading.Event()


def flush():
    with lock:
        lines = buf[:]
        buf.clear()
    if not SITE or (not lines and not first[0]):
        return
    try:
        r = requests.post(f"{SITE}/.netlify/functions/logs", headers=H, timeout=10,
                          json={"name": name, "token": tok, "lines": lines, "reset": first[0]})
        if r.ok:
            first[0] = False
            return
    except Exception:
        pass
    with lock:                       # keep the lines for the next try
        buf[:0] = lines


def pump():
    while not done.wait(2):
        flush()


threading.Thread(target=pump, daemon=True).start()
flush()                              # clears the previous night's output right away
for line in sys.stdin:
    line = ANSI.sub("", line.rstrip("\n"))
    print(f"[{name}] {line}", flush=True)
    with lock:
        buf.append(line)
done.set()
flush()
