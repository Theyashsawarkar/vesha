"""Accounts, profiles, folder rules and usage.

Every account is a Claude Code *profile*: a config folder Claude Code uses
when CLAUDE_CONFIG_DIR points at it. The account you were already signed in
to keeps ~/.claude as its profile ("main"); every other account gets
~/.local/state/vesha/profiles/<name>. A login lives in exactly one profile:
Claude Code rotates refresh tokens, so two copies of one login would sign
each other out.

Your shared setup (CLAUDE.md, settings, skills, plugins, agents, commands,
and, by default, conversation history) is linked from ~/.claude into every
other profile, so each account behaves the same.
"""
import json
import os
import re
import shutil
import time
import tomllib
import urllib.error
import urllib.request

HOME = os.path.expanduser("~")
# Accounts and profiles live in the state folder: ~/.local/share/vesha is where
# installers (kosha, install.sh) put vesha itself.
DATA = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.join(HOME, ".local/state"), "vesha")
LEGACY = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.join(HOME, ".local/share"), "vesha")   # before v0.1.1
CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.join(HOME, ".cache"), "vesha")
CONFIG = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(HOME, ".config"), "vesha", "config.toml")
MAIN_DIR = os.path.join(HOME, ".claude")
MAIN_JSON = os.path.join(HOME, ".claude.json")
PROFILES = os.path.join(DATA, "profiles")
STATE = os.path.join(DATA, "accounts.json")
BIN = os.path.join(HOME, ".local", "bin")

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"   # Claude Code's public OAuth client
BETA = "oauth-2025-04-20"
UA = "vesha/0.1 (+https://github.com/Theyashsawarkar/vesha)"

# Shared from ~/.claude into every other profile.
SHARED = ["CLAUDE.md", "settings.json", "skills", "plugins", "agents", "commands", "output-styles", "keybindings.json"]
HISTORY = ["projects", "history.jsonl", "todos", "file-history", "plans"]

DEFAULTS = {"warn_at": 85, "switch_at": 98, "auto": True, "share_history": True, "usage_ttl": 180, "check_every": 120}
NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


class VeshaError(Exception):
    pass


def config():
    conf = dict(DEFAULTS)
    try:
        with open(CONFIG, "rb") as f:
            conf.update(tomllib.load(f).get("vesha", {}))
    except (OSError, tomllib.TOMLDecodeError):
        pass
    return conf


# ===================================================================== state
def migrate():
    """Moves accounts and profiles from where v0.1.0 kept them (the folder
    vesha itself installs into) to DATA. Once, and only out of a folder that
    isn't a checkout."""
    old = os.path.join(LEGACY, "accounts.json")
    if not os.path.exists(old) or os.path.exists(STATE) or os.path.isdir(os.path.join(LEGACY, ".git")):
        return
    if any(d.startswith(LEGACY + os.sep) for d in running_profiles()):
        return   # a session runs on an old profile: move once it's gone
    os.makedirs(DATA, mode=0o700, exist_ok=True)
    for item in ("accounts.json", "profiles"):
        if os.path.lexists(os.path.join(LEGACY, item)):
            os.replace(os.path.join(LEGACY, item), os.path.join(DATA, item))
    try:
        os.rmdir(LEGACY)   # only if nothing else is left
    except OSError:
        pass


def load():
    migrate()
    try:
        with open(STATE) as f:
            st = json.load(f)
    except (OSError, ValueError):
        st = {}
    st.setdefault("accounts", {})
    st.setdefault("folders", {})
    st.setdefault("default", None)
    return st


def write_private(path, data, **dump):
    """Writes JSON readable only by you (0600 from creation), atomically."""
    tmp = path + ".vesha-tmp"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        json.dump(data, f, **dump)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def save(st):
    os.makedirs(DATA, exist_ok=True)
    write_private(STATE, st, indent=2, sort_keys=True)


def check_name(name):
    if not NAME.match(name or ""):
        raise VeshaError(f"“{name}” isn't a good name: lowercase letters, digits, - and _, up to 32")
    return name


# ===================================================================== profiles
def profile_dir(st, name):
    a = st["accounts"].get(name)
    if not a:
        raise VeshaError(f"no account called {name}")
    return MAIN_DIR if a.get("main") else os.path.join(PROFILES, name)


def env_for(st, name):
    """The environment changes that make Claude Code use this account."""
    d = profile_dir(st, name)
    return {} if d == MAIN_DIR else {"CLAUDE_CONFIG_DIR": d}


def read_credentials(d):
    try:
        with open(os.path.join(d, ".credentials.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def read_profile_json(d):
    path = MAIN_JSON if d == MAIN_DIR else os.path.join(d, ".claude.json")
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def identity(d):
    """What Claude Code knows about the account signed in to this profile."""
    cj = read_profile_json(d).get("oauthAccount") or {}
    cred = (read_credentials(d) or {}).get("claudeAiOauth") or {}
    plan = (cred.get("subscriptionType") or "").capitalize()
    tier = cred.get("rateLimitTier") or ""
    m = re.search(r"max_(\d+)x", tier)
    if m:
        plan = f"Max ({m.group(1)}x)"
    return {"email": cj.get("emailAddress", ""), "name": cj.get("displayName") or cj.get("fullName", ""),
            "org": cj.get("organizationName", ""), "plan": plan or "–", "uuid": cj.get("accountUuid", ""),
            "signed_in": bool(cred.get("refreshToken") or cred.get("accessToken")),
            "login_expires": (cred.get("refreshTokenExpiresAt") or 0) / 1000 or None}


def login_copied(d, refresh_token):
    """Whether another profile (or ~/.claude) holds this same login."""
    dirs = [MAIN_DIR] + ([os.path.join(PROFILES, x) for x in os.listdir(PROFILES)] if os.path.isdir(PROFILES) else [])
    for other in dirs:
        if os.path.realpath(other) != os.path.realpath(d):
            if ((read_credentials(other) or {}).get("claudeAiOauth") or {}).get("refreshToken") == refresh_token:
                return True
    return False


def login_problems(st):
    """{name: [problem]}: profiles now signed in to a different account than
    the one added (claude-swap or a /login inside it changed it), and logins
    copied between profiles (they share a refresh token: when one renews it,
    the other is logged out)."""
    out, seen = {}, {}
    for n, a in st["accounts"].items():
        d = profile_dir(st, n)
        who = identity(d)
        if not who["signed_in"]:
            continue
        if a.get("email") and (who["email"], who["org"]) != (a.get("email"), a.get("org")):
            out.setdefault(n, []).append(
                f"now signed in to {who['email']} ({who['org'] or 'no org'}), not the account added as {n}: "
                f"another tool or a /login changed it")
        rt = ((read_credentials(d) or {}).get("claudeAiOauth") or {}).get("refreshToken")
        if rt and rt in seen:
            out.setdefault(n, []).append(f"holds a copy of {seen[rt]}'s login: when one renews it, the other is logged out")
        elif rt:
            seen[rt] = n
    return out


def link_shared(d, share_history=True):
    """Links ~/.claude's shared setup into a profile (never over real files)."""
    os.makedirs(d, exist_ok=True)
    os.chmod(d, 0o700)
    for item in SHARED + (HISTORY if share_history else []):
        src, dst = os.path.join(MAIN_DIR, item), os.path.join(d, item)
        if not os.path.lexists(src):
            if item in ("projects", "todos", "file-history", "plans"):
                os.makedirs(src, exist_ok=True)
            else:
                continue
        if os.path.islink(dst):
            if os.readlink(dst) == src:
                continue
            os.remove(dst)
        elif os.path.exists(dst):
            continue   # the profile has its own: leave it
        os.symlink(src, dst)


def adopt_main(st, name):
    """Registers the account already signed in to ~/.claude, in place."""
    if any(a.get("main") for a in st["accounts"].values()):
        raise VeshaError("the account in ~/.claude is already added")
    who = identity(MAIN_DIR)
    if not who["signed_in"]:
        raise VeshaError("Claude Code isn't signed in yet: run `claude` and sign in, or `vesha add <name>`")
    st["accounts"][check_name(name)] = {"main": True, "email": who["email"], "org": who["org"], "plan": who["plan"],
                                        "added": int(time.time()), "paused": False}
    st["default"] = st["default"] or name
    save(st)
    return who


def new_profile(st, name):
    check_name(name)
    if name in st["accounts"]:
        raise VeshaError(f"there's already an account called {name}")
    d = os.path.join(PROFILES, name)
    link_shared(d, config()["share_history"])
    return d


def register(st, name, d):
    who = identity(d)
    if not who["signed_in"]:
        raise VeshaError("no login in the profile: the sign-in didn't finish")
    for other, a in st["accounts"].items():
        if who["email"] and a.get("email") == who["email"] and who["org"] == a.get("org"):
            raise VeshaError(f"that's the same account as {other} ({who['email']})")
    st["accounts"][name] = {"main": False, "email": who["email"], "org": who["org"], "plan": who["plan"],
                            "added": int(time.time()), "paused": False}
    st["default"] = st["default"] or name
    save(st)
    return who


def remove(st, name):
    a = st["accounts"].get(name)
    if not a:
        raise VeshaError(f"no account called {name}")
    if not a.get("main"):
        shutil.rmtree(os.path.join(PROFILES, name), ignore_errors=True)
    del st["accounts"][name]
    st["folders"] = {f: n for f, n in st["folders"].items() if n != name}
    if st["default"] == name:
        st["default"] = next(iter(st["accounts"]), None)
    save(st)


def rename(st, old, new):
    check_name(new)
    if old not in st["accounts"]:
        raise VeshaError(f"no account called {old}")
    if new in st["accounts"]:
        raise VeshaError(f"there's already an account called {new}")
    a = st["accounts"].pop(old)
    if not a.get("main"):
        os.rename(os.path.join(PROFILES, old), os.path.join(PROFILES, new))
    st["accounts"][new] = a
    st["folders"] = {f: (new if n == old else n) for f, n in st["folders"].items()}
    if st["default"] == old:
        st["default"] = new
    save(st)


# ===================================================================== which account
def resolve(st, cwd=None, env=None):
    """(account, why) for a new Claude started here: this terminal
    (VESHA_ACCOUNT), then the nearest folder rule, then the default."""
    env = os.environ if env is None else env
    forced = env.get("VESHA_ACCOUNT")
    if forced:
        if forced in st["accounts"]:
            return forced, "this terminal"
    cwd = os.path.realpath(cwd or os.getcwd())
    best = None
    for folder, name in st["folders"].items():
        f = os.path.realpath(os.path.expanduser(folder))
        if (cwd == f or cwd.startswith(f.rstrip("/") + "/")) and name in st["accounts"]:
            if best is None or len(f) > len(best[0]):
                best = (f, name)
    if best:
        return best[1], f"folder {best[0].replace(HOME, '~')}"
    if st["default"] in st["accounts"]:
        return st["default"], "the default"
    return None, "no accounts yet"


def map_folder(st, name, folder):
    if name not in st["accounts"]:
        raise VeshaError(f"no account called {name}")
    f = os.path.realpath(os.path.expanduser(folder))
    if not os.path.isdir(f):
        raise VeshaError(f"{folder} isn't a folder")
    st["folders"][f.replace(HOME, "~", 1) if f.startswith(HOME) else f] = name
    save(st)
    return f


def unmap_folder(st, folder):
    f = os.path.realpath(os.path.expanduser(folder))
    keys = [k for k in st["folders"] if os.path.realpath(os.path.expanduser(k)) == f]
    if not keys:
        raise VeshaError(f"no rule for {folder}")
    for k in keys:
        del st["folders"][k]
    save(st)


# ===================================================================== running claude
def real_claude():
    """The real claude, skipping vesha's own wrapper."""
    me = os.path.realpath(os.path.join(BIN, "claude"))
    for d in os.environ.get("PATH", "").split(":"):
        cand = os.path.join(d, "claude")
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            if os.path.realpath(cand) == me and is_shim(cand):
                continue
            if is_shim(cand):
                continue
            return cand
    raise VeshaError("Claude Code isn't installed (no `claude` on PATH)")


def is_shim(path):
    try:
        with open(path, "rb") as f:
            return b"vesha-shim" in f.read(400)
    except OSError:
        return False


def signal_bar():
    """Tells waybar, and any running `vesha waybar`, to redraw now (SIGRTMIN+12).
    Only processes whose command is exactly `… vesha waybar` get it: the
    signal's default action would end anything else."""
    import signal
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                cmd = [c.decode(errors="ignore") for c in f.read().split(b"\0") if c]
        except OSError:
            continue
        mine = len(cmd) >= 2 and cmd[-1] == "waybar" and os.path.basename(cmd[-2]) == "vesha"
        if mine or (cmd and os.path.basename(cmd[0]) == "waybar"):   # waybar handles every real-time signal
            try:
                os.kill(int(pid), signal.SIGRTMIN + 12)
            except OSError:
                pass


def running_profiles():
    """Profiles in use by running Claude Code processes: {profile_dir: count}."""
    out = {}
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                cmd = f.read().split(b"\0")
            if not any(os.path.basename(c.decode(errors="ignore")) in ("claude", "cli.js") for c in cmd[:2]):
                continue
            with open(f"/proc/{pid}/environ", "rb") as f:
                env = dict(e.split(b"=", 1) for e in f.read().split(b"\0") if b"=" in e)
        except OSError:
            continue
        d = env.get(b"CLAUDE_CONFIG_DIR", b"").decode() or MAIN_DIR
        out[os.path.realpath(d)] = out.get(os.path.realpath(d), 0) + 1
    return out


# ===================================================================== usage
def _cache():
    try:
        with open(os.path.join(CACHE, "usage.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_cache(c):
    os.makedirs(CACHE, exist_ok=True)
    tmp = os.path.join(CACHE, "usage.json.tmp")
    with open(tmp, "w") as f:
        json.dump(c, f)
    os.replace(tmp, os.path.join(CACHE, "usage.json"))


def _refresh(d, cred):
    """Renews an expired access token, writing the new tokens back to the
    profile's only copy. Skipped while Claude is running on the profile:
    Claude refreshes it itself, and two refreshes would race."""
    oauth = cred.get("claudeAiOauth") or {}
    if not oauth.get("refreshToken"):
        raise VeshaError("signed out: sign in again")
    if running_profiles().get(os.path.realpath(d)):
        raise VeshaError("token renewing in Claude")
    if login_copied(d, oauth["refreshToken"]):   # renewing would log the other copy out
        raise VeshaError("login copied in another profile: see vesha doctor")
    body = json.dumps({"grant_type": "refresh_token", "refresh_token": oauth["refreshToken"], "client_id": CLIENT_ID}).encode()
    req = urllib.request.Request(TOKEN_URL, data=body, headers={"Content-Type": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        msg = "login expired: sign in again (vesha login)" if e.code in (400, 401) else f"token renewal failed ({e.code})"
        raise VeshaError(msg) from None
    oauth["accessToken"] = data["access_token"]
    if data.get("refresh_token"):
        oauth["refreshToken"] = data["refresh_token"]
    oauth["expiresAt"] = int((time.time() + data.get("expires_in", 3600)) * 1000)
    cred["claudeAiOauth"] = oauth
    write_private(os.path.join(d, ".credentials.json"), cred)
    return oauth["accessToken"]


def fetch_usage(d):
    """{five_hour: {pct, resets_at}, seven_day: {...}} for one profile."""
    cred = read_credentials(d)
    if not cred:
        raise VeshaError("no login")
    oauth = cred.get("claudeAiOauth") or {}
    token = oauth.get("accessToken")
    if not token or (oauth.get("expiresAt") or 0) / 1000 < time.time() + 60:
        token = _refresh(d, cred)
    req = urllib.request.Request(USAGE_URL, headers={"Authorization": f"Bearer {token}", "anthropic-beta": BETA,
                                                     "User-Agent": UA, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise VeshaError("login expired: sign in again") from None
        if e.code == 429:
            raise VeshaError("asked too often: try again in a minute") from None
        raise VeshaError(f"usage unavailable ({e.code})") from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise VeshaError("offline") from e
    out = {}
    for key in ("five_hour", "seven_day", "seven_day_opus"):
        w = data.get(key)
        if isinstance(w, dict) and w.get("utilization") is not None:
            out[key] = {"pct": round(float(w["utilization"])), "resets_at": w.get("resets_at")}
    return out


def usage(st, names=None, fresh=False, on_start=None, on_done=None):
    """{name: usage dict or VeshaError}, cached for usage_ttl seconds."""
    import concurrent.futures
    names = list(names or st["accounts"])
    ttl = config()["usage_ttl"]
    cache = _cache()
    out, ask = {}, []
    for n in names:
        hit = cache.get(n)
        if not fresh and hit and time.time() - hit.get("at", 0) < ttl:
            out[n] = hit["usage"]
            if on_done:
                on_done(n, out[n], True)
        else:
            ask.append(n)

    def one(n):
        if on_start:
            on_start(n)
        return fetch_usage(profile_dir(st, n))
    if ask:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            futs = {ex.submit(one, n): n for n in ask}
            for f in concurrent.futures.as_completed(futs):
                n = futs[f]
                try:
                    out[n] = f.result()
                    cache[n] = {"usage": out[n], "at": time.time()}
                except Exception as e:
                    out[n] = e if isinstance(e, VeshaError) else VeshaError(str(e))
                    if cache.get(n):   # show the last known numbers, marked stale
                        out[n] = dict(cache[n]["usage"], stale=str(out[n]))
                if on_done:
                    on_done(n, out[n], False)
        _save_cache(cache)
    return out


def resets_in(iso):
    """'1h 18m' / '2d 15h' until an ISO time, and the local clock time."""
    if not iso:
        return "", ""
    from datetime import datetime
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return "", ""
    s = max(0, t - time.time())
    if s >= 86400:
        rel = f"{int(s // 86400)}d {int(s % 86400 // 3600)}h"
    elif s >= 3600:
        rel = f"{int(s // 3600)}h {int(s % 3600 // 60)}m"
    else:
        rel = f"{int(s // 60)}m"
    lt = time.localtime(t)
    clock = time.strftime("%-I:%M %p" if s < 86400 else "%a %-I %p", lt)
    return rel, clock


def best_alternative(st, use, exclude):
    """The unpaused account with the most room left (judged by the fuller of
    its 5-hour and weekly windows), other than exclude."""
    cands = []
    for n, a in st["accounts"].items():
        u = use.get(n)
        if n == exclude or a.get("paused") or not isinstance(u, dict) or "five_hour" not in u or u.get("stale"):
            continue
        limit = config()["switch_at"]
        if u["five_hour"]["pct"] >= limit or u.get("seven_day", {}).get("pct", 0) >= limit:
            continue   # no room there either
        h5, wk = u["five_hour"]["pct"], u.get("seven_day", {}).get("pct", 0)
        cands.append((max(h5, wk), h5, n))   # the most room in its fuller window
    return min(cands)[2] if cands else None


# ===================================================================== claude-swap import
def import_cswap(st, names=None):
    """Brings claude-swap's accounts across: the one signed in to ~/.claude
    becomes the main account; every other gets its own profile with its
    saved login. Returns [(name, email, kind)]."""
    root = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.join(HOME, ".local/share"), "claude-swap")
    if not os.path.isdir(os.path.join(root, "credentials")):
        legacy = os.path.join(HOME, ".claude-swap-backup")
        root = legacy if os.path.isdir(os.path.join(legacy, "credentials")) else root
    creds_dir, conf_dir = os.path.join(root, "credentials"), os.path.join(root, "configs")
    if not os.path.isdir(creds_dir):
        raise VeshaError("no claude-swap accounts found (looked in ~/.local/share/claude-swap)")
    try:
        seq = json.load(open(os.path.join(root, "sequence.json")))
    except (OSError, ValueError):
        seq = {}
    aliases = {}
    for k, v in (seq.get("accounts") or {}).items() if isinstance(seq.get("accounts"), dict) else []:
        if isinstance(v, dict) and v.get("alias"):
            aliases[v.get("email", k)] = v["alias"]
    main_email = identity(MAIN_DIR)["email"]
    done = []

    def pick_name(email, org):
        if org.endswith("'s Organization") or not org:
            org = "personal"   # Claude names a personal account's organisation after you
        base = aliases.get(email) or (re.sub(r"[^a-z0-9_-]+", "-", org.lower()).strip("-")[:24] or "account")
        n, i = base, 2
        while n in st["accounts"]:
            n, i = f"{base}-{i}", i + 1
        return n
    if main_email and not any(a.get("main") for a in st["accounts"].values()):
        who = identity(MAIN_DIR)
        n = (names or {}).get(main_email) or pick_name(main_email, who["org"])
        adopt_main(st, n)
        done.append((n, main_email, "main (~/.claude)"))
    # claude-swap's files: credentials/.<kind>-<n>-<email>.<ext> (base64 JSON), configs/.<kind>-<n>-<email>.json
    pattern = re.compile(r"^\.?[a-z-]+?-(\d+)-(.+@.+?)\.[a-z]+$")
    configs = {}
    for f in os.listdir(conf_dir) if os.path.isdir(conf_dir) else []:
        m = pattern.match(f)
        if m:
            configs[m.group(2)] = os.path.join(conf_dir, f)
    for fname in sorted(os.listdir(creds_dir)):
        m = pattern.match(fname)
        email = m.group(2) if m else fname
        path = os.path.join(creds_dir, fname)
        if email == main_email or any(a.get("email") == email for a in st["accounts"].values()):
            continue
        cred = None
        raw = open(path, "rb").read()
        for decode in (lambda b: json.loads(b), lambda b: json.loads(__import__("base64").b64decode(b))):
            try:
                cred = decode(raw)
                break
            except (ValueError, TypeError):
                continue
        if not isinstance(cred, dict) or "claudeAiOauth" not in cred:
            continue
        conf = {}
        cpath = configs.get(email)
        if cpath:
            try:
                conf = json.load(open(cpath))
            except (OSError, ValueError):
                conf = {}
        oa = conf.get("oauthAccount") if isinstance(conf, dict) else None
        org = (oa or {}).get("organizationName", "")
        n = (names or {}).get(email) or pick_name(email, org)
        d = new_profile(st, n)
        write_private(os.path.join(d, ".credentials.json"), cred)
        base_conf = {k: v for k, v in read_profile_json(MAIN_DIR).items()
                     if k in ("hasCompletedOnboarding", "lastOnboardingVersion", "theme", "editorMode", "autoUpdates")}
        base_conf["hasCompletedOnboarding"] = True
        if oa:
            base_conf["oauthAccount"] = oa
        with open(os.path.join(d, ".claude.json"), "w") as f:
            json.dump(base_conf, f, indent=2)
        os.chmod(os.path.join(d, ".claude.json"), 0o600)
        st["accounts"][n] = {"main": False, "email": email, "org": org, "plan": identity(d)["plan"],
                             "added": int(time.time()), "paused": False}
        done.append((n, email, "own profile"))
    save(st)
    return done


# ===================================================================== shim
SHIM = """#!/bin/sh
# vesha-shim: runs Claude Code as the right account for this folder (vesha which).
# Remove with `vesha uninstall-shim`.
exec "{vesha}" exec-claude "$@"
"""


def install_shim(vesha_path):
    link = os.path.join(BIN, "claude")
    if os.path.exists(link) and not is_shim(link):
        raise VeshaError(f"{link} exists and isn't vesha's: move it away first")
    os.makedirs(BIN, exist_ok=True)
    with open(link, "w") as f:
        f.write(SHIM.format(vesha=vesha_path))
    os.chmod(link, 0o755)
    return link


def uninstall_shim():
    link = os.path.join(BIN, "claude")
    if is_shim(link):
        os.remove(link)
        return link
    return None
