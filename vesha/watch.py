"""The watcher (`vesha watch`, run by vesha.service): it keeps an eye on the
active account's 5-hour and weekly usage. Near a limit it warns, with a
button to switch; at `switch_at` it switches to the account with the most
room left (when automatic switching is on). Running Claude sessions in
~/.claude follow the switch from their next message.

Its numbers come first from Claude Code itself: every session's status line
runs `vesha feed`, which records the limits Claude got with its last reply
and wakes the watcher (SIGUSR1) when they matter. The usage endpoint is only
asked when those are missing or old, and never while it says 429."""
import json
import os
import signal
import subprocess
import threading
import time

from . import core

LOG = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.join(core.HOME, ".local/state"), "vesha", "watch.log")
WARNED = os.path.join(os.path.dirname(LOG), "warned.json")   # what was said, so a restart doesn't say it again
PID = os.path.join(core.CACHE, "watch.pid")   # for `vesha feed` to wake us
WAKE = threading.Event()


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
    """(pct, which window) of the fuller of the 5-hour and weekly windows,
    as far as they can be known (core.effective: last known numbers are
    lower bounds until their window resets)."""
    w = [(p, k) for k, p in core.effective(u).items()]
    return max(w) if w else (0, None)


def window_id(iso):
    """A limit window, by its reset time rounded to 10 minutes: the API's
    resets_at jitters by up to a second between fetches."""
    from datetime import datetime
    try:
        return round(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() / 600)
    except (AttributeError, ValueError):
        return None


def limit_key(u):
    """The fullest window of an account and which one of it (by reset time):
    what a warning is remembered by."""
    pct, window = worst(u)
    return (window, window_id(u.get(window, {}).get("resets_at"))) if window else None


# Switch to an account that is full too only when it frees up at least this
# much sooner: reset times jitter, and two accounts resetting together
# mustn't make the watcher flip between them.
SOONER = 60


def first_free(st, use, conf, active):
    """When every account is at its limit: the other account to wait on
    instead of the active one, because its limit resets sooner; else None."""
    other = core.earliest_free(st, use, active)
    if not other:
        return None
    mine = core.free_at(use[active], conf["switch_at"])
    return other[0] if mine is None or other[1] < mine - SOONER else None


def decide(st, use, conf, warned):
    """What to do about the active account's usage: returns (action, info):
    ("switch", alt) | ("switch_first", alt) | ("full", alt-or-None) |
    ("warn", alt-or-None) | ("ok", None). "switch_first": every account is at
    its limit and alt's resets first, so it's the one to be on. warned
    remembers what was already said for each limit window, so each warning
    is shown once per window."""
    active = st["default"]
    u = use.get(active)
    if not active or len(st["accounts"]) < 2 or not isinstance(u, dict):
        return "ok", None
    pct, window = worst(u)
    resets = limit_key(u)
    alt = core.best_alternative(st, use, active)
    if pct >= conf["switch_at"]:
        if conf["auto"] and alt:
            return "switch", alt
        if conf["auto"] and not alt:
            first = first_free(st, use, conf, active)
            if first:
                warned[active] = ("full", resets)   # said in the switch's notification
                return "switch_first", first
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


def ttls(conf, near):
    """How old (seconds) the active account's and the others' numbers may be
    before the usage endpoint is asked. The status line keeps the active
    one's current whenever Claude is in use; the others change only when a
    session runs on them directly, so they are asked rarely."""
    return (60 if near else conf["usage_ttl"]), max(600, conf["usage_ttl"])


def tick(warned, state):
    """One check; returns how long to wait before the next."""
    conf = core.config()
    st = core.load()
    active = st["default"]
    if not active or len(st["accounts"]) < 2:
        return conf["check_every"]
    t_active, t_others = ttls(conf, state.get("near", False))
    use = core.usage(st, [active], ttl=t_active)
    pct, _ = worst(use.get(active)) if isinstance(use.get(active), dict) else (0, None)
    if pct >= conf["warn_at"]:   # an alternative is about to matter
        use.update(core.usage(st, [n for n in st["accounts"] if n != active], ttl=t_others))
    else:
        use.update({n: (core._cache().get(n) or {}).get("usage") for n in st["accounts"] if n != active})
    if isinstance(use.get(active), dict) and use[active].get("stale") and state.get("stale") != use[active]["stale"]:
        log(f"{active}: using its last known numbers ({use[active]['stale']})")
    state["stale"] = use[active].get("stale") if isinstance(use.get(active), dict) else None
    action, alt = decide(st, use, conf, warned)
    u = use.get(active) if isinstance(use.get(active), dict) else {}
    pct, window = worst(u) if u else (0, None)
    label = "5-hour" if window == "five_hour" else "weekly"
    _, clock = core.resets_in(u.get(window, {}).get("resets_at") if window else None)
    if action == "switch":
        if not switch_to(st, alt, f"{active} at {pct}% of its {label} limit"):
            return 20   # Claude was renewing the login, or similar: soon again
        state["near"] = False
        a5 = core.effective(use[alt]).get("five_hour", 0)
        notify(f"Claude: switched to {alt}", f"{active} reached its {label} limit (it resets {clock}).\n"
               f"Every Claude session uses {alt} ({a5}% used) from its next message.")
    elif action == "switch_first":
        if not switch_to(st, alt, f"every account at its limit; {alt} frees up first"):
            return 20
        state["near"] = True
        _, alt_clock = core.resets_in(_iso_or_none(core.free_at(use[alt], conf["switch_at"])))
        warned[alt] = ("full", limit_key(use[alt]))   # this notification says it; no second one
        notify(f"Claude: every account is at its limit: switched to {alt}",
               f"{alt} frees up first, {alt_clock} ({active}: {clock}).\n"
               f"Every Claude session uses {alt} from its next message.", "critical")
    elif action == "full":
        if alt:
            msg = f"{alt} has room: vesha switch {alt}"
        else:
            first = core.earliest_free(st, use, active)
            _, fclock = core.resets_in(_iso_or_none(first[1])) if first else ("", "")
            msg = f"every other account is at its limit too; {first[0]} frees up first, {fclock}" if first \
                else "every other account is at its limit too"
        notify(f"Claude: {active} reached its {label} limit", f"It resets {clock}; {msg}.", "critical")
    elif action == "warn":
        if alt:
            a5 = core.effective(use[alt]).get("five_hour", 0)

            def ask():
                if notify(f"Claude: {active} at {pct}% of its {label} limit", f"Switch new sessions to {alt} ({a5}% used)?",
                          "normal", {"switch": f"Switch to {alt}"}) == "switch":
                    s2 = core.load()
                    if s2["default"] == active:
                        switch_to(s2, alt, "chosen from the notification")
            threading.Thread(target=ask, daemon=True).start()
        else:
            notify(f"Claude: {active} at {pct}% of its {label} limit", f"It resets {clock}.")
    st = core.load()
    u = use.get(st["default"]) if isinstance(use.get(st["default"]), dict) else {}
    pct, _ = worst(u) if u else (0, None)
    near = pct >= conf["warn_at"]
    state["near"] = near
    delay = min(conf["check_every"], 60) if near else conf["check_every"]
    return min(delay, until_free(st, use, conf)) if pct >= conf["switch_at"] else delay


def until_free(st, use, conf, now=None):
    """Seconds until the first unpaused account's limit resets (a few
    seconds after, so the reset has happened): when every account is full,
    the watcher looks again right then instead of up to check_every later."""
    now = now or time.time()
    times = [t for n, a in st["accounts"].items() if not a.get("paused") and isinstance(use.get(n), dict)
             for t in [core.free_at(use[n], conf["switch_at"], now)] if t is not None and t > now]
    return max(5, min(times) - now + 5) if times else 3600


def _iso_or_none(epoch):
    return core._iso(epoch) if epoch else None


def run():
    log("watcher started")
    signal.signal(signal.SIGUSR1, lambda *_: WAKE.set())
    os.makedirs(core.CACHE, exist_ok=True)
    with open(PID, "w") as f:
        f.write(str(os.getpid()))
    try:
        with open(WARNED) as f:
            warned = {n: (k, tuple(r)) for n, (k, r) in json.load(f).items()}
    except (OSError, ValueError, TypeError):
        warned = {}
    state = {}
    while True:
        try:
            before = dict(warned)
            delay = tick(warned, state)
            if warned != before:
                with open(WARNED + ".tmp", "w") as f:
                    json.dump(warned, f)
                os.replace(WARNED + ".tmp", WARNED)
        except Exception as e:   # the watcher must never die on a bad answer
            log(f"error: {e!r}")
            delay = 300
        WAKE.wait(delay)
        WAKE.clear()


if __name__ == "__main__":
    run()
