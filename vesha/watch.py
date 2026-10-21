"""The watcher (`vesha watch`, run by vesha.service): every couple of minutes
it checks the active account's usage. Near a limit it warns, with a button to
switch; at the limit it switches to the account with the most room left
(when automatic switching is on). Running Claude sessions keep their
account; new ones, in every folder, use the new active one."""
import json
import os
import subprocess
import threading
import time

from . import core

LOG = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.join(core.HOME, ".local/state"), "vesha", "watch.log")
WARNED = os.path.join(os.path.dirname(LOG), "warned.json")   # what was said, so a restart doesn't say it again


def log(msg):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")


def notify(title, body, urgency="normal", actions=None):
    """A notification; with actions, waits (in a thread) for the click."""
    log(f"notify: {title}")
    args = ["notify-send", "-a", "vesha", "-u", urgency, "-i", "avatar-default-symbolic",
            "-h", "string:x-canonical-private-synchronous:vesha", title, body]
    if not actions:
        subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return None
    for key, label in actions.items():
        args[1:1] = ["-A", f"{key}={label}"]
    r = subprocess.run(args, capture_output=True, text=True)
    return r.stdout.strip() or None


def switch_to(st, name, why):
    """Moves `name`'s login into ~/.claude (core.activate). Returns False, and
    says why, when it can't."""
    old = st["default"]
    try:
        core.activate(st, name)
    except core.VeshaError as e:
        log(f"couldn't switch {old} -> {name}: {e}")
        notify(f"Claude: couldn't switch to {name}", str(e), "critical")
        return False
    core.signal_bar()
    log(f"switched {old} -> {name} ({why})")
    return True


def worst(u):
    """(pct, which window) of the fuller of the 5-hour and weekly windows."""
    w = [(u[k]["pct"], k) for k in ("five_hour", "seven_day") if k in u]
    return max(w) if w else (0, None)


def window_id(iso):
    """A limit window, by its reset time rounded to 10 minutes: the API's
    resets_at jitters by up to a second between fetches."""
    from datetime import datetime
    try:
        return round(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() / 600)
    except (AttributeError, ValueError):
        return None


def decide(st, use, conf, warned):
    """What to do about the active account's usage: returns (action, info):
    ("switch", alt) | ("full", alt-or-None) | ("warn", alt-or-None) | ("ok", None).
    warned remembers what was already said for each limit window, so each
    warning is shown once per window."""
    active = st["default"]
    u = use.get(active)
    if not active or len(st["accounts"]) < 2 or not isinstance(u, dict) or u.get("stale"):
        return "ok", None
    pct, window = worst(u)
    resets = (window, window_id(u.get(window, {}).get("resets_at"))) if window else None
    alt = core.best_alternative(st, use, active)
    if pct >= conf["switch_at"]:
        if conf["auto"] and alt:
            return "switch", alt
        if warned.get(active) == ("full", resets):
            return "ok", None
        warned[active] = ("full", resets)
        return "full", alt
    if pct >= conf["warn_at"]:
        if warned.get(active) == ("warn", resets):
            return "ok", None
        warned[active] = ("warn", resets)
        return "warn", alt
    return "ok", None


def tick(warned):
    """One check; returns how long to wait before the next."""
    conf = core.config()
    st = core.load()
    active = st["default"]
    if not active or len(st["accounts"]) < 2:
        return conf["check_every"]
    use = core.usage(st, fresh=True)
    action, alt = decide(st, use, conf, warned)
    u = use.get(active) if isinstance(use.get(active), dict) else {}
    pct, window = worst(u) if u else (0, None)
    label = "5-hour" if window == "five_hour" else "weekly"
    _, clock = core.resets_in(u.get(window, {}).get("resets_at") if window else None)
    if action == "switch":
        if not switch_to(st, alt, f"{active} at {pct}% of its {label} limit"):
            return conf["check_every"]
        a5 = use[alt].get("five_hour", {}).get("pct", 0)
        notify(f"Claude: switched to {alt}", f"{active} reached its {label} limit (it resets {clock}).\n"
               f"Every Claude session uses {alt} ({a5}% used) from its next message.")
    elif action == "full":
        msg = f"{alt} has room: vesha switch {alt}" if alt else "every other account is at its limit too"
        notify(f"Claude: {active} reached its {label} limit", f"It resets {clock}; {msg}.", "critical")
    elif action == "warn":
        if alt:
            a5 = use[alt].get("five_hour", {}).get("pct", 0)

            def ask():
                if notify(f"Claude: {active} at {pct}% of its {label} limit", f"Switch new sessions to {alt} ({a5}% used)?",
                          "normal", {"switch": f"Switch to {alt}"}) == "switch":
                    s2 = core.load()
                    if s2["default"] == active:
                        switch_to(s2, alt, "chosen from the notification")
            threading.Thread(target=ask, daemon=True).start()
        else:
            notify(f"Claude: {active} at {pct}% of its {label} limit", f"It resets {clock}.")
    near = pct >= conf["warn_at"]
    return min(conf["check_every"], 60) if near else conf["check_every"]


def run():
    log("watcher started")
    try:
        with open(WARNED) as f:
            warned = {n: (k, tuple(r)) for n, (k, r) in json.load(f).items()}
    except (OSError, ValueError, TypeError):
        warned = {}
    while True:
        try:
            before = dict(warned)
            delay = tick(warned)
            if warned != before:
                with open(WARNED + ".tmp", "w") as f:
                    json.dump(warned, f)
                os.replace(WARNED + ".tmp", WARNED)
        except Exception as e:   # the watcher must never die on a bad answer
            log(f"error: {e!r}")
            delay = 300
        time.sleep(delay)


if __name__ == "__main__":
    run()
