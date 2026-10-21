"""vesha's commands, their help, and their output."""
import json
import os
import shutil
import subprocess
import sys
import time

from . import VERSION, core, ui
from .core import VeshaError
from .ui import c

COMMANDS = {
    "switch": dict(group="Switch", aliases=["sw", "s"], args="[<account>]",
                   summary="Make an account the active one (no name: the next one)",
                   description="Every new `claude`, in any folder, uses the active account (unless this terminal or a "
                               "folder rule says otherwise). Claude sessions already running keep theirs.",
                   examples=["vesha switch personal", "vesha sw", "vesha switch work"]),
    "list": dict(group="Switch", aliases=["ls", "status"], args="[--json] [-r]",
                 summary="Every account: plan, usage, which is active",
                 options=[("--json", "machine-readable"), ("-r, --refresh", "ask for usage now instead of the last 3 minutes'")],
                 examples=["vesha list", "vesha ls --json"]),
    "usage": dict(group="Switch", aliases=["u"], args="[-r]",
                  summary="The 5-hour and weekly limits of every account, with reset times",
                  examples=["vesha usage", "vesha u -r"]),
    "which": dict(group="Switch", aliases=["w"], args="",
                  summary="The account a new claude would use here, and why",
                  examples=["vesha which"]),
    "run": dict(group="Switch", aliases=["r"], args="<account> [-- <command>]",
                summary="Run claude (or any command) as an account, just this once",
                examples=["vesha run work", "vesha run personal -- claude -p 'hello'"]),
    "use": dict(group="Switch", aliases=[], args="<account> | --clear",
                summary="This terminal only (needs the shell hook: eval \"$(vesha init zsh)\")",
                examples=["vesha use work", "vesha use --clear"]),
    "auto": dict(group="Limits", aliases=[], args="on|off",
                 summary="Switch the active account by itself when it hits its limit",
                 description="With auto on (the default) and the watcher running (`vesha service install`), the active "
                             "account is switched to the one with the most room left when its 5-hour or weekly limit "
                             "is reached; you get a notification either way. Paused accounts are never picked.",
                 examples=["vesha auto on", "vesha auto off"]),
    "pause": dict(group="Limits", aliases=[], args="<account>",
                  summary="Keep an account out of automatic switching", examples=["vesha pause client-x"]),
    "resume": dict(group="Limits", aliases=[], args="<account>",
                   summary="Let a paused account be picked again", examples=["vesha resume client-x"]),
    "add": dict(group="Accounts", aliases=["login"], args="<name> [email] [--current]",
                summary="Sign in a new account (or the one already in ~/.claude with --current)",
                description="Opens Claude Code's sign-in in your browser for a fresh profile, with the email filled in "
                            "when you give one: enter the code Anthropic emails you there, and the account is added. In "
                            "the switcher, a does the same without leaving it. `--current` adds the account "
                            "Claude Code is already signed in to, in place. `vesha login <name>` signs an existing account "
                            "in again after its login expired.",
                examples=["vesha add work2 you@company.com", "vesha add personal --current", "vesha login personal"]),
    "repair": dict(group="Accounts", aliases=["fix"], args="[-y]",
                   summary="Fix profiles whose login another tool replaced (claude-swap, a /login)",
                   description="When ~/.claude ends up holding another account's login (claude-swap switched it, or a "
                               "/login there), vesha shows the wrong account and two profiles share one login, which logs "
                               "one of them out on the next token renewal. repair makes the records match the logins, moves "
                               "the duplicate profile to vesha's trash folder, and tells you which account to sign in again. "
                               "It shows the plan and asks first. `vesha doctor` says when it's needed.",
                   examples=["vesha repair", "vesha login personal"]),
    "remove": dict(group="Accounts", aliases=["rm"], args="<account> [-y]",
                   summary="Forget an account (and delete its profile)", examples=["vesha rm client-x"]),
    "rename": dict(group="Accounts", aliases=["mv"], args="<old> <new>",
                   summary="Give an account a new name", examples=["vesha rename acme-inc work"]),
    "import": dict(group="Accounts", aliases=[], args="cswap",
                   summary="Bring your claude-swap accounts across",
                   description="The account Claude Code is signed in to stays in ~/.claude; every other gets its own profile "
                               "with its saved login. After importing, don't switch with claude-swap any more (its copies go "
                               "stale): uninstall it once you're happy.",
                   examples=["vesha import cswap"]),
    "map": dict(group="Folders", aliases=[], args="<account> [<folder>]",
                summary="Optional: a folder (and everything under it) always uses an account",
                examples=["vesha map personal ~/personal"]),
    "unmap": dict(group="Folders", aliases=[], args="[<folder>]", summary="Remove a folder rule",
                  examples=["vesha unmap ~/personal"]),
    "install-shim": dict(group="Setup", aliases=[], args="",
                         summary="Put vesha's `claude` wrapper on PATH (needed for switching)",
                         description="A tiny ~/.local/bin/claude that starts the real Claude Code as the account `vesha which` "
                                     "picks. It must come before the real claude on your PATH.",
                         examples=["vesha install-shim"]),
    "uninstall-shim": dict(group="Setup", aliases=[], args="", summary="Remove the wrapper", examples=["vesha uninstall-shim"]),
    "service": dict(group="Setup", aliases=[], args="install|remove|status",
                    summary="The background watcher: warns near limits, switches at them",
                    examples=["vesha service install", "vesha service status"]),
    "init": dict(group="Setup", aliases=[], args="zsh|bash",
                 summary="The shell hook for `vesha use` and tab completion",
                 examples=["eval \"$(vesha init zsh)\"   # in ~/.zshrc"]),
    "doctor": dict(group="Setup", aliases=["check"], args="",
                   summary="Check every account, the wrapper and the watcher", examples=["vesha doctor"]),
    "waybar": dict(group="Setup", aliases=[], args="", summary="JSON for a waybar module (the active account and its usage)",
                   examples=["vesha waybar"]),
    "help": dict(group="Help", aliases=[], args="[<command>]", summary="This overview, or one command in detail",
                 examples=["vesha help", "vesha help switch"]),
}
GROUPS = ["Switch", "Limits", "Accounts", "Folders", "Setup", "Help"]
ALIASES = {a: n for n, d in COMMANDS.items() for a in d["aliases"]}
GLOBAL = [("-y, --yes", "don't ask"), ("--json", "machine-readable output (list, usage, which)"),
          ("--no-color", "plain output (also NO_COLOR=1)"), ("-h, --help", "help for vesha or a command"),
          ("-V, --version", "the version")]


def logo():
    return c("❯", "peach", bold=True) + c(" vesha", "text", bold=True) + c(" वेष", "peach") + c(f"  v{VERSION}", "dim")


def help_all():
    ui.out(logo() + c("   every Claude Code account, one key away", "sub"))
    ui.out()
    ui.out(f"{c('Usage', 'text', bold=True)}  vesha {c('[command]', 'peach')} {c('[options]', 'dim')}"
           f"      {c('vesha alone opens the switcher (vim keys, ? inside for help)', 'dim')}")
    nw = max(len(n) for n in COMMANDS) + 2
    for g in GROUPS:
        ui.out()
        ui.out(c(g.upper(), "peach", bold=True))
        for n, d in COMMANDS.items():
            if d["group"] == g:
                al = c(f" ({', '.join(d['aliases'])})", "dim") if d["aliases"] else ""
                ui.out(f"  {c(ui.pad(n, nw), 'mauve')}{d['summary']}{al}")
    ui.out()
    ui.out(c("OPTIONS", "peach", bold=True))
    for o, d in GLOBAL:
        ui.out(f"  {c(ui.pad(o, 16), 'sky')}{d}")
    ui.out()
    ui.out(c("Docs: https://theyashsawarkar.github.io/vesha/   ·   vesha <command> --help for any command", "dim"))


def help_cmd(name):
    import textwrap
    d = COMMANDS[name]
    ui.out(logo())
    ui.out()
    ui.out(f"{c('vesha ' + name, 'peach', bold=True)} {c(d['args'], 'sky')}")
    ui.out(f"  {d['summary']}")
    if d.get("description"):
        ui.out()
        for line in textwrap.wrap(d["description"], min(ui.cols(), 90) - 2):
            ui.out(f"  {c(line, 'sub')}")
    if d["aliases"]:
        ui.out()
        ui.out(f"{c('ALIASES', 'peach', bold=True)}  {', '.join(d['aliases'])}")
    if d.get("options"):
        ui.out()
        ui.out(c("OPTIONS", "peach", bold=True))
        for o, w in d["options"]:
            ui.out(f"  {c(ui.pad(o, 18), 'sky')}{w}")
    ui.out()
    ui.out(c("EXAMPLES", "peach", bold=True))
    for ex in d["examples"]:
        ui.out(f"  {c('$', 'faint')} {ex}")


def suggest(word, choices):
    import difflib
    m = difflib.get_close_matches(word, choices, n=1, cutoff=0.6)
    return m[0] if m else None


class Ctx:
    def __init__(self, args):
        self.yes = bool({"-y", "--yes"} & set(args))
        self.json = "--json" in args
        self.fresh = bool({"-r", "--refresh"} & set(args))
        self.flags = {a for a in args if a.startswith("-")}
        if "--" in args:
            i = args.index("--")
            self.args, self.rest = [a for a in args[:i] if not a.startswith("-")], args[i + 1:]
        else:
            self.args, self.rest = [a for a in args if not a.startswith("-")], []
        self.t0 = time.monotonic()


def need(st, name):
    if name not in st["accounts"]:
        s = suggest(name, list(st["accounts"]))
        raise VeshaError(f"no account called {c(name, 'text', bold=True)}" + (f" (did you mean {c(s, 'peach')}?)" if s else "")
                         + c("  vesha list shows them", "dim"))
    return st["accounts"][name]


def badge_color(pct):
    """Green while there's plenty left, yellow from half, red from the warning level."""
    return "red" if pct >= core.config()["warn_at"] else "yellow" if pct >= 50 else "green"


TRACK = (49, 50, 68)   # Catppuccin surface0: the empty part of a bar


def bar(pct, width=20):
    """A pill, like the switcher's: rounded ends, a soft track, the fill drawn
    to an eighth of a cell. Plain `[####----]` without colour."""
    pct = max(0, min(100, int(pct)))
    inner = max(1, width - 2)
    eighths = round(inner * 8 * pct / 100)
    if not ui.TTY:
        fill = round(inner * pct / 100)
        return "[" + "#" * fill + "-" * (inner - fill) + "]"
    r, g, b = ui._COLORS[badge_color(pct)]
    fg, track = f"38;2;{r};{g};{b}", "48;2;{};{};{}".format(*TRACK)
    tfg = "38;2;{};{};{}".format(*TRACK)
    cells = "".join("█" if (part := max(0, min(8, eighths - i * 8))) == 8 else " ▏▎▍▌▋▊▉"[part] for i in range(inner))
    left = fg if eighths else tfg
    right = fg if eighths >= inner * 8 else tfg
    return f"\033[{left}m\ue0b6\033[0m\033[{fg};{track}m{cells}\033[0m\033[{right}m\ue0b4\033[0m"


def usage_cell(u, key="five_hour", w=10):
    if isinstance(u, VeshaError) or not isinstance(u, dict) or key not in u:
        return c("–", "faint")
    p = u[key]["pct"]
    rel, _ = core.resets_in(u[key].get("resets_at"))
    return f"{bar(p, w)} {c(f'{p:>3}%', badge_color(p), bold=True)} {c(rel, 'dim')}"


def board_usage(st, names, fresh, title="Checking usage"):
    """Fetches usage with a live row per account (no board when all cached)."""
    use_cache = not fresh and all(core._cache().get(n) and time.time() - core._cache()[n].get("at", 0) < core.config()["usage_ttl"]
                                  for n in names)
    if use_cache or not names:
        return core.usage(st, names, fresh)
    with ui.Progress(names, title, "asking") as board:
        def start(n):
            board.set(n, "run", "asking Anthropic…")

        def done(n, u, cached):
            if isinstance(u, VeshaError):
                board.set(n, "warn", c(str(u), "yellow"))
            else:
                h = u.get("five_hour", {}).get("pct")
                w = u.get("seven_day", {}).get("pct")
                stale = c("  (last known)", "dim") if u.get("stale") else ""
                board.set(n, "ok", f"5h {c(h, badge_color(h or 0), bold=True)}%  ·  week {w}%{stale}" if h is not None else "no usage data")
        return core.usage(st, names, fresh, start, done)


# ===================================================================== switch
def cmd_list(ctx):
    st = core.load()
    if not st["accounts"]:
        ui.warn("no accounts yet")
        ui.note("vesha import cswap   ·   vesha add <name> --current   ·   vesha add <name>")
        return 0
    names = list(st["accounts"])
    use = core.usage(st, names, ctx.fresh) if ctx.json else board_usage(st, names, ctx.fresh)
    here, why = core.resolve(st)
    running = core.running_profiles()
    if ctx.json:
        out = []
        for n, a in st["accounts"].items():
            u = use.get(n)
            out.append({"name": n, "email": a.get("email"), "org": a.get("org"), "plan": a.get("plan"),
                        "active": n == st["default"], "here": n == here, "paused": a.get("paused", False),
                        "main": a.get("main", False), "usage": u if isinstance(u, dict) else None,
                        "error": str(u) if isinstance(u, VeshaError) else None})
        ui.out(json.dumps(out, indent=2))
        return 0
    rows = []
    for n, a in st["accounts"].items():
        tags = []
        if n == st["default"]:
            tags.append(c("● active", "peach", bold=True))
        if n == here and n != st["default"]:
            tags.append(c("◆ here", "sky"))
        if a.get("paused"):
            tags.append(c("paused", "dim"))
        live = running.get(os.path.realpath(core.profile_dir(st, n)), 0)
        if live:
            tags.append(c(f"{live} running", "green"))
        u = use.get(n)
        err = c(str(u), "yellow") if isinstance(u, VeshaError) else ""
        rows.append([c(n, "text", bold=True), c(a.get("email") or "–", "sub"), c(a.get("plan") or "–", "lavender"),
                     err or usage_cell(u, "five_hour"), "" if err else usage_cell(u, "seven_day"), "  ".join(tags)])
    ui.table(rows, ["Account", "Email", "Plan", "5 hours", "Week", ""], title="Accounts")
    ui.out(f"{c('New claude here →', 'dim')} {c(here, 'peach', bold=True)} {c('(' + why + ')', 'dim')}")
    return 0


def cmd_switch(ctx):
    st = core.load()
    if not st["accounts"]:
        raise VeshaError("no accounts yet: vesha import cswap, or vesha add <name>")
    if ctx.args:
        name = ctx.args[0]
        need(st, name)
    else:
        names = list(st["accounts"])
        i = names.index(st["default"]) if st["default"] in names else -1
        name = names[(i + 1) % len(names)]
    old = st["default"]
    st["default"] = name
    core.save(st)
    notify_bar()
    a = st["accounts"][name]
    ui.ok(f"{c(name, 'peach', bold=True)} is active {c('(' + (a.get('email') or '') + ')', 'dim')}"
          + (c(f"   was {old}", "dim") if old and old != name else ""))
    if not core.is_shim(os.path.join(core.BIN, "claude")):
        ui.warn("the claude wrapper isn't installed, so plain `claude` won't follow: vesha install-shim")
    else:
        live = sum(core.running_profiles().values())
        mapped = sum(1 for n in st["folders"].values() if n != name)
        where = "in every folder" + (f" without a folder rule ({mapped} have one)" if mapped else "")
        running = f"; {live} running session{'s' if live != 1 else ''} keep{'s' if live == 1 else ''} its account" if live else ""
        ui.note(f"new claude sessions use it, {where}{running}")
    return 0


def notify_bar():
    """Tells a running waybar module to redraw now."""
    core.signal_bar()


def cmd_usage(ctx):
    st = core.load()
    names = list(st["accounts"])
    if not names:
        raise VeshaError("no accounts yet")
    use = core.usage(st, names, ctx.fresh) if ctx.json else board_usage(st, names, ctx.fresh)
    if ctx.json:
        ui.out(json.dumps({n: (u if isinstance(u, dict) else {"error": str(u)}) for n, u in use.items()}, indent=2))
        return 0
    ui.header("Usage")
    nw = max(len(n) for n in names)
    warn_at = core.config()["warn_at"]
    near = set()
    for n in names:
        u = use.get(n)
        mark = c(" ●", "peach") if n == st["default"] else "  "
        if isinstance(u, VeshaError):
            ui.out(f"{c(ui.pad(n, nw), 'text', bold=True)}{mark}  {c(str(u), 'yellow')}")
            continue
        for i, (key, label) in enumerate((("five_hour", "5h"), ("seven_day", "wk"))):
            if key not in u:
                continue
            p = u[key]["pct"]
            rel, clock = core.resets_in(u[key].get("resets_at"))
            if p >= warn_at:
                near.add(n)
            name = c(ui.pad(n, nw), "text", bold=True) + mark if i == 0 else " " * (nw + 2)
            ui.out(f"{name}  {c(label, 'dim')} {bar(p)} {c(f'{p:>3}%', badge_color(p), bold=True)}  "
                   f"{c('resets ' + clock, 'dim')} {c('(in ' + rel + ')', 'faint') if rel else ''}")
        if u.get("stale"):
            ui.out(" " * (nw + 6) + c(f"last known numbers ({u['stale']})", "faint"))
    ok_n = sum(1 for n, u in use.items() if isinstance(u, dict) and n not in near)
    failed = sum(1 for u in use.values() if not isinstance(u, dict))
    ui.summary([("Room left", ok_n, "green"), ("Near a limit", len(near), "red"), ("Couldn't check", failed, "yellow")])
    return 0


def cmd_which(ctx):
    st = core.load()
    name, why = core.resolve(st)
    if ctx.json:
        ui.out(json.dumps({"account": name, "why": why, "env": core.env_for(st, name) if name else {}}))
        return 0
    if not name:
        raise VeshaError("no accounts yet")
    ui.out(f"{c(name, 'peach', bold=True)}  {c(why, 'dim')}  {c(st['accounts'][name].get('email', ''), 'sub')}")
    return 0


def exec_claude(args, name=None):
    st = core.load()
    real = core.real_claude()
    why = "asked for"
    if name is None:
        name, why = core.resolve(st)
    env = dict(os.environ)
    if name:
        env.update(core.env_for(st, name))
        if core.profile_dir(st, name) == core.MAIN_DIR:
            env.pop("CLAUDE_CONFIG_DIR", None)
        env["VESHA_ACTIVE"] = name
        if sys.stderr.isatty() and not os.environ.get("VESHA_QUIET") and not any(a in args for a in ("-p", "--print", "--version", "-v")):
            u = core._cache().get(name, {}).get("usage", {}).get("five_hour", {})
            extra = f" · {u['pct']}% of 5h used" if u else ""
            sys.stderr.write(c("vesha ▸ ", "dim") + c(name, "peach", bold=True) + c(f" ({why}){extra}", "dim") + "\n")
    os.execve(real, [real, *args], env)


def cmd_run(ctx):
    if not ctx.args:
        raise VeshaError("which account? vesha run <account> [-- command]")
    st = core.load()
    name = ctx.args[0]
    need(st, name)
    if ctx.rest and ctx.rest[0] != "claude":
        env = dict(os.environ, **core.env_for(st, name), VESHA_ACTIVE=name)
        if core.profile_dir(st, name) == core.MAIN_DIR:
            env.pop("CLAUDE_CONFIG_DIR", None)
        os.execvpe(ctx.rest[0], ctx.rest, env)
    exec_claude(ctx.rest[1:] if ctx.rest else [], name)


def cmd_use(ctx):
    hook = c('eval "$(vesha init zsh)"', "peach")
    sys.stderr.write(c("! ", "yellow", bold=True) + "`vesha use` needs the shell hook to change this terminal:\n"
                     f"   add {hook} to ~/.zshrc (or bash), then open a new terminal\n"
                     f"   just once: {c('export VESHA_ACCOUNT=<account>', 'peach')}\n")
    return 1


# ===================================================================== limits
def cmd_auto(ctx):
    on = (ctx.args or ["status"])[0]
    if on not in ("on", "off", "status"):
        raise VeshaError("vesha auto on|off")
    path = core.CONFIG
    conf = {}
    try:
        import tomllib
        conf = tomllib.load(open(path, "rb")).get("vesha", {})
    except (OSError, ValueError):
        pass
    if on != "status":
        conf["auto"] = on == "on"
        write_config(conf)
    state = core.config()["auto"]
    ui.ok(f"automatic switching is {c('on', 'green', bold=True) if state else c('off', 'red', bold=True)}"
          + c(f"  (at {core.config()['switch_at']}% of a limit)" if state else "", "dim"))
    if state and not service_active():
        ui.warn("the watcher isn't running: vesha service install")
    return 0


def write_config(conf):
    os.makedirs(os.path.dirname(core.CONFIG), exist_ok=True)
    lines = ["# vesha settings (vesha help auto)", "[vesha]"]
    for k, v in conf.items():
        lines.append(f"{k} = {json.dumps(v) if not isinstance(v, bool) else str(v).lower()}")
    open(core.CONFIG, "w").write("\n".join(lines) + "\n")


def cmd_pause(ctx, on):
    if not ctx.args:
        raise VeshaError("which account?")
    st = core.load()
    for n in ctx.args:
        need(st, n)["paused"] = on
        ui.ok(f"{c(n, 'text', bold=True)} " + ("won't be picked by automatic switching" if on else "can be picked again"))
    core.save(st)
    return 0


# ===================================================================== accounts
def cmd_add(ctx):
    st = core.load()
    if not ctx.args:
        raise VeshaError("name it: vesha add <name>   (vesha add <name> --current for the account already signed in)")
    name = core.check_name(ctx.args[0])
    if name in st["accounts"] and "--login" in ctx.flags:
        return relogin(st, name)
    if "--current" in ctx.flags:
        who = core.adopt_main(st, name)
        ui.ok(f"added {c(name, 'peach', bold=True)} {c('(' + who['email'] + ', the login already in ~/.claude)', 'dim')}")
        return 0
    email = next((a for a in ctx.args[1:] if "@" in a), "")
    d = core.new_profile(st, name)
    ui.header(f"Signing in {name}")
    ui.note("a tab opens in your browser" + (f" with {email} filled in" if email else "")
            + ": enter the code Anthropic emails you there; if the page then shows a code, paste it here")
    env = dict(os.environ, CLAUDE_CONFIG_DIR=d)
    r = subprocess.run([core.real_claude(), "auth", "login", "--claudeai"] + (["--email", email] if email else []), env=env)
    try:
        who = core.register(st, name, d)
    except VeshaError:
        shutil.rmtree(d, ignore_errors=True)
        raise
    if r.returncode != 0 and not who:
        raise VeshaError("the sign-in didn't finish")
    ui.ok(f"added {c(name, 'peach', bold=True)} {c('(' + who['email'] + ', ' + who['plan'] + ')', 'dim')}")
    ui.note(f"vesha switch {name} makes it the active account")
    return 0


def relogin(st, name):
    d = core.profile_dir(st, name)
    a = st["accounts"][name]
    ui.header(f"Signing {name} in again")
    if a.get("email"):
        ui.note(f"sign in as {c(a['email'], 'text', bold=True)}" + (f" ({a['org']})" if a.get("org") else ""))
    env = dict(os.environ)
    if d != core.MAIN_DIR:
        core.link_shared(d, core.config()["share_history"])
        env["CLAUDE_CONFIG_DIR"] = d
    subprocess.run([core.real_claude(), "auth", "login", "--claudeai"] + (["--email", a["email"]] if a.get("email") else []), env=env)
    who = core.identity(d)
    if not who["signed_in"]:
        raise VeshaError("still not signed in")
    for other, o in st["accounts"].items():
        if other != name and (o.get("email"), o.get("org")) == (who["email"], who["org"]):
            raise VeshaError(f"that's {other}'s account ({who['email']}): run vesha login {name} again and pick "
                             f"{a.get('email') or 'the other account'} in the browser")
    st["accounts"][name].update(email=who["email"], org=who["org"], plan=who["plan"])
    core.save(st)
    ui.ok(f"{c(name, 'peach', bold=True)} is signed in {c('(' + who['email'] + ')', 'dim')}")
    return 0


def cmd_repair(ctx):
    st = core.load()
    plan = core.repair_plan(st)
    if not plan:
        ui.ok("every profile holds the login vesha expects: nothing to repair")
        return 0
    ui.header("Repair")
    for text, _ in plan:
        ui.out(f"  {c('•', 'peach')} {text}")
    ui.out()
    if not ui.confirm(assume=True if ctx.yes else None):
        return 1
    for _, act in plan:
        act(st)
    core.save(st)
    notify_bar()
    ui.ok("repaired")
    for n, a in st["accounts"].items():
        if not core.identity(core.profile_dir(st, n))["signed_in"]:
            ui.note(f"{n} isn't signed in: {c('vesha login ' + n, 'peach', bold=True)}"
                    + (f" (pick {a['email']})" if a.get("email") else ""))
    return 0


def cmd_remove(ctx):
    if not ctx.args:
        raise VeshaError("which account?")
    st = core.load()
    name = ctx.args[0]
    a = need(st, name)
    where = core.profile_dir(st, name).replace(core.HOME, "~")
    what = "forget it (its login stays in ~/.claude)" if a.get("main") else f"delete its profile ({where})"
    if not ui.confirm(f"Remove {name}? This will {what}.", default=False, assume=True if ctx.yes else None):
        ui.warn("nothing changed")
        return 1
    core.remove(st, name)
    ui.ok(f"removed {c(name, 'text', bold=True)}" + (c(f"   {st['default']} is active now", "dim") if st["default"] else ""))
    return 0


def cmd_rename(ctx):
    if len(ctx.args) != 2:
        raise VeshaError("vesha rename <old> <new>")
    st = core.load()
    core.rename(st, *ctx.args)
    ui.ok(f"{ctx.args[0]} is now {c(ctx.args[1], 'peach', bold=True)}")
    return 0


def cmd_import(ctx):
    if (ctx.args or ["cswap"])[0] not in ("cswap", "claude-swap"):
        raise VeshaError("vesha import cswap")
    st = core.load()
    done = core.import_cswap(st)
    if not done:
        ui.ok("nothing new: every claude-swap account is already here")
        return 0
    ui.table([[c(n, "peach", bold=True), c(e, "sub"), c(k, "dim")] for n, e, k in done], ["Account", "Email", "Profile"],
             title="Imported from claude-swap")
    ui.note("rename them: vesha rename <old> <new>  ·  then vesha usage")
    ui.warn("from now on switch with vesha, not cswap (its saved logins go stale); uninstall it when you're happy")
    return 0


# ===================================================================== folders
def cmd_map(ctx):
    if not ctx.args:
        st = core.load()
        if not st["folders"]:
            ui.note("no folder rules: every folder uses the active account")
            return 0
        rows = [[c(f, "sky"), c(n, "peach", bold=True)] for f, n in sorted(st["folders"].items())]
        ui.table(rows, ["Folder", "Account"], title="Folders")
        return 0
    st = core.load()
    folder = ctx.args[1] if len(ctx.args) > 1 else os.getcwd()
    f = core.map_folder(st, ctx.args[0], folder)
    ui.ok(f"{c(f.replace(core.HOME, '~'), 'sky')} and below use {c(ctx.args[0], 'peach', bold=True)}")
    return 0


def cmd_unmap(ctx):
    st = core.load()
    folder = ctx.args[0] if ctx.args else os.getcwd()
    core.unmap_folder(st, folder)
    ui.ok(f"{folder.replace(core.HOME, '~')} uses the active account again")
    return 0


# ===================================================================== setup
def self_path():
    """This vesha, by a path that survives reinstalls: ~/.local/bin/vesha when it points here
    (kosha moves the checkout between releases and `kosha link`s, never the link)."""
    here = os.path.realpath(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", "vesha"))
    onpath = os.path.join(core.BIN, "vesha")
    return onpath if os.path.realpath(onpath) == here else here


def cmd_install_shim(ctx):
    link = core.install_shim(self_path())
    ui.ok(f"installed {c(link.replace(core.HOME, '~'), 'sky')}: plain `claude` now follows the active account")
    first = shutil.which("claude")
    if first and os.path.realpath(first) != os.path.realpath(link):
        ui.warn(f"{first} comes first on your PATH: put {core.BIN} before it")
    return 0


def cmd_uninstall_shim(ctx):
    link = core.uninstall_shim()
    (ui.ok(f"removed {link}") if link else ui.note("the wrapper wasn't installed"))
    return 0


UNIT = """[Unit]
Description=vesha: warn near Claude usage limits, switch accounts at them

[Service]
ExecStart={python} -I {vesha} watch
Restart=on-failure
RestartSec=30

[Install]
WantedBy=default.target
"""


def unit_path():
    return os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(core.HOME, ".config"), "systemd", "user", "vesha.service")


def service_active():
    if not os.path.exists(unit_path()):
        return False
    r = subprocess.run(["systemctl", "--user", "is-active", "vesha.service"], capture_output=True, text=True)
    return r.stdout.strip() == "active"


def cmd_service(ctx):
    what = (ctx.args or ["status"])[0]
    unit = unit_path()
    if what == "install":
        os.makedirs(os.path.dirname(unit), exist_ok=True)
        open(unit, "w").write(UNIT.format(python=sys.executable, vesha=self_path()))
        subprocess.run(["systemctl", "--user", "daemon-reload"])
        subprocess.run(["systemctl", "--user", "enable", "--now", "vesha.service"], capture_output=True)
        subprocess.run(["systemctl", "--user", "restart", "vesha.service"], capture_output=True)
        if service_active():
            ui.ok("the watcher is running (vesha.service)")
        else:
            ui.err("the watcher didn't start: journalctl --user -u vesha")
    elif what == "remove":
        subprocess.run(["systemctl", "--user", "disable", "--now", "vesha.service"], capture_output=True)
        if os.path.exists(unit):
            os.remove(unit)
        subprocess.run(["systemctl", "--user", "daemon-reload"])
        ui.ok("the watcher is stopped and removed")
    else:
        ui.ok("the watcher is running") if service_active() else ui.warn("the watcher isn't running: vesha service install")
        from .watch import LOG
        try:
            with open(LOG) as f:
                tail = f.read().splitlines()[-8:]
        except OSError:
            tail = []
        if tail:
            ui.out(c(f"\nlast from {LOG.replace(core.HOME, '~')}:", "dim"))
            for line in tail:
                ui.out("  " + c(line[:19], "faint") + " " + line[20:])
    return 0


def cmd_watch(ctx):
    """The watcher (run by vesha.service): checks the active account's usage,
    warns near its limit, switches when it's reached."""
    from .watch import run
    return run()


def cmd_init(ctx):
    shell = (ctx.args or [os.path.basename(os.environ.get("SHELL", "zsh"))])[0]
    names_cmd = "vesha _names"
    cmds = " ".join(list(COMMANDS) + list(ALIASES))
    acct_cmds = "switch|sw|s|run|r|use|pause|resume|remove|rm|rename|mv|map|login"
    func = """vesha() {
  if [ "$1" = use ]; then
    if [ "$2" = --clear ] || [ -z "$2" ]; then unset VESHA_ACCOUNT; echo "this terminal follows the active account again"
    elif command vesha _names | grep -qx -- "$2"; then export VESHA_ACCOUNT="$2"; echo "this terminal uses $2"
    else command vesha which >/dev/null; echo "no account called $2" >&2; return 1; fi
  else command vesha "$@"; fi
}"""
    if shell == "zsh":
        ui.out(func + f"""
_vesha() {{
  local -a cmds accts
  cmds=({cmds})
  if (( CURRENT == 2 )); then _describe 'command' cmds
  else case ${{words[2]}} in
    {acct_cmds}) accts=(${{(f)"$({names_cmd})"}}); _describe 'account' accts ;;
    help) _describe 'command' cmds ;; init) _values 'shell' zsh bash ;; auto) _values 'state' on off ;;
    service) _values 'action' install remove status ;; import) _values 'from' cswap ;;
  esac; fi
}}
(( $+functions[compdef] )) && compdef _vesha vesha""")
    elif shell == "bash":
        ui.out(func + f"""
_vesha() {{
  local cur=${{COMP_WORDS[COMP_CWORD]}}
  if [ "$COMP_CWORD" -eq 1 ]; then COMPREPLY=($(compgen -W "{cmds}" -- "$cur")); return; fi
  case ${{COMP_WORDS[1]}} in {acct_cmds}) COMPREPLY=($(compgen -W "$({names_cmd})" -- "$cur")) ;; esac
}}
complete -F _vesha vesha""")
    else:
        raise VeshaError("vesha init zsh|bash")
    return 0


def cmd_doctor(ctx):
    st = core.load()
    ui.header("Doctor")
    problems = 0
    real = None
    try:
        real = core.real_claude()
        ui.ok(f"Claude Code: {c(real, 'sub')}")
    except VeshaError as e:
        ui.err(str(e))
        problems += 1
    shim = os.path.join(core.BIN, "claude")
    first = shutil.which("claude")
    if core.is_shim(shim):
        if first and os.path.realpath(first) == os.path.realpath(shim):
            ui.ok("the claude wrapper is installed and first on PATH")
        else:
            ui.warn(f"the wrapper is installed but {first} comes first on PATH")
            problems += 1
    else:
        ui.warn("the claude wrapper isn't installed (vesha install-shim): plain `claude` won't follow the active account")
        problems += 1
    if core.config()["auto"]:
        (ui.ok("the watcher is running (automatic switching on)") if service_active()
         else (ui.warn("automatic switching is on but the watcher isn't running: vesha service install"), None)[1])
        problems += 0 if service_active() else 1
    logins = core.login_problems(st)
    for n, a in st["accounts"].items():
        d = core.profile_dir(st, n)
        who = core.identity(d)
        issues = list(logins.get(n, []))
        if issues:
            issues.append(f"fix: {c('vesha repair', 'peach', bold=True)}")
        if not who["signed_in"]:
            issues.append(f"signed out: vesha login {n}")
        if who["login_expires"] and who["login_expires"] < time.time() + 7 * 86400:
            issues.append(f"its login expires soon: vesha login {n}")
        if not a.get("main") and os.path.isdir(d):   # a profile is made when the account signs in
            for item in core.SHARED[:2]:
                src = os.path.join(core.MAIN_DIR, item)
                if os.path.exists(src) and not os.path.islink(os.path.join(d, item)):
                    issues.append(f"{item} isn't shared from ~/.claude")
        if issues:
            problems += 1
            ui.warn(c(n, "text", bold=True))
            for i in issues:
                ui.out(f"    {c('└', 'faint')} {i}")
        else:
            ui.ok(f"{n} {c(who['email'] + ' · ' + who['plan'], 'dim')}")
    ui.out()
    if problems:
        ui.warn("1 thing needs attention" if problems == 1 else f"{problems} things need attention")
    else:
        ui.ok(c("all good", "green", bold=True))
    return 1 if problems else 0


def cmd_waybar(ctx):
    """One JSON line per change: the active account and its 5-hour usage.
    Redraws on SIGRTMIN+12 (sent by `vesha switch`) and every minute."""
    import signal
    import threading
    ev = threading.Event()
    signal.signal(signal.SIGRTMIN + 12, lambda *_: ev.set())
    last = None
    while True:
        out = {"text": "", "class": "none", "tooltip": ""}
        try:
            st = core.load()
            name = st["default"]
            if name and len(st["accounts"]) > 1:
                u = core.usage(st, [name]).get(name)
                h = u.get("five_hour", {}) if isinstance(u, dict) else {}
                p = h.get("pct")
                rel, clock = core.resets_in(h.get("resets_at"))
                conf = core.config()
                cls = "unknown" if p is None else "full" if p >= conf["switch_at"] else "warn" if p >= conf["warn_at"] else "ok"
                lines = [f"Claude: {name}  ({st['accounts'][name].get('email', '')})"]
                use_all = core.usage(st)
                for n in st["accounts"]:
                    un = use_all.get(n)
                    if isinstance(un, dict) and "five_hour" in un:
                        r5, c5 = core.resets_in(un["five_hour"].get("resets_at"))
                        lines.append(f"{'●' if n == name else '○'} {n}: 5h {un['five_hour']['pct']}% (resets {c5})"
                                     + (f" · week {un['seven_day']['pct']}%" if "seven_day" in un else ""))
                lines += ["", "Click: the switcher · Scroll: the next account"]
                out = {"text": f"{name} {p}%" if p is not None else name, "class": cls, "tooltip": "\n".join(lines),
                       "percentage": p or 0, "alt": cls}
        except Exception as e:
            out = {"text": "", "class": "error", "tooltip": str(e)}
        line = json.dumps(out)
        if line != last:
            try:
                print(line, flush=True)
            except BrokenPipeError:
                return 0
            last = line
        ev.wait(60)
        ev.clear()


HANDLERS = {"list": cmd_list, "switch": cmd_switch, "usage": cmd_usage, "which": cmd_which, "run": cmd_run, "use": cmd_use,
            "auto": cmd_auto, "pause": lambda x: cmd_pause(x, True), "resume": lambda x: cmd_pause(x, False),
            "add": cmd_add, "repair": cmd_repair, "remove": cmd_remove, "rename": cmd_rename, "import": cmd_import, "map": cmd_map,
            "unmap": cmd_unmap, "install-shim": cmd_install_shim, "uninstall-shim": cmd_uninstall_shim,
            "service": cmd_service, "init": cmd_init, "doctor": cmd_doctor, "waybar": cmd_waybar, "watch": cmd_watch}


def main(argv):
    if "--no-color" in argv:
        ui.set_color(False)
        argv = [a for a in argv if a != "--no-color"]
    if argv and argv[0] == "exec-claude":   # the wrapper: as fast and quiet as possible
        try:
            exec_claude(argv[1:])
        except VeshaError as e:
            sys.stderr.write(f"vesha: {e}\n")
            return 127
    if not argv:
        if not sys.stdout.isatty():
            return HANDLERS["list"](Ctx([])) or 0
        from .tui import run as tui
        return tui()
    cmd, rest = argv[0], argv[1:]
    if cmd in ("-h", "--help"):
        help_all()
        return 0
    if cmd in ("-V", "--version", "version"):
        ui.out(f"vesha {VERSION}")
        return 0
    if cmd == "_names":
        ui.out("\n".join(core.load()["accounts"]))
        return 0
    if cmd == "watch":   # internal: the systemd unit's long-running loop
        return cmd_watch(Ctx(rest)) or 0
    if cmd == "login":
        rest = rest + ["--login"]
    cmd = ALIASES.get(cmd, cmd)
    if cmd == "help":
        if rest and ALIASES.get(rest[0], rest[0]) in COMMANDS:
            help_cmd(ALIASES.get(rest[0], rest[0]))
        else:
            help_all()
        return 0
    if cmd not in COMMANDS:
        s = suggest(cmd, list(COMMANDS) + list(ALIASES))
        ui.err(f"no command {c(cmd, 'text', bold=True)}" + (f": did you mean {c('vesha ' + s, 'peach', bold=True)}?" if s else "")
               + c("   vesha help lists them", "dim"))
        return 2
    if {"-h", "--help"} & set(rest):
        help_cmd(cmd)
        return 0
    try:
        return HANDLERS[cmd](Ctx(rest)) or 0
    except VeshaError as e:
        ui.err(str(e))
        return 1
    except KeyboardInterrupt:
        ui.out()
        return 130
