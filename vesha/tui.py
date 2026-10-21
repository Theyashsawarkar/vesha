"""The full-screen switcher (`vesha` with no arguments). Vim keys:

  j k ↓ ↑   move        gg G   top, bottom     Ctrl-d Ctrl-u  half a page
  1-9       jump to that account               Tab  accounts ⇄ folder rules
  Enter s   make it the active account         r    run claude as it, here
  u         refresh usage                      p    pause / resume (auto-switching)
  m         this folder always uses it         a    sign in a new account, right here
  R cw      rename                             dd   remove (asks)
  y         copy the email                     /    filter, n N next / previous
  ?         all keys                           q Esc quit
"""
import curses
import os
import re
import subprocess
import threading
import time

from . import core

# keybind: Vesha/switcher | j / k | Move down / up an account (counts work: 3j)
# keybind: Vesha/switcher | gg / G | Jump to the first / last account
# keybind: Vesha/switcher | Ctrl+d / Ctrl+u | Scroll half a page down / up
# keybind: Vesha/switcher | 1-9 | Jump to that account
# keybind: Vesha/switcher | Tab | Switch between accounts and folder rules
# keybind: Vesha/switcher | h / l | Go to the accounts / folder rules tab
# keybind: Vesha/switcher | Enter / s | Switch to the account (make it active)
# keybind: Vesha/switcher | r | Run claude as the account, in this folder
# keybind: Vesha/switcher | u | Refresh usage now
# keybind: Vesha/switcher | p | Toggle pause (out of automatic switching)
# keybind: Vesha/switcher | m | Map this folder to the account
# keybind: Vesha/switcher | a | Add an account (sign in)
# keybind: Vesha/switcher | R / cw | Rename the account
# keybind: Vesha/switcher | dd | Remove the account, or the folder rule (asks)
# keybind: Vesha/switcher | y | Copy the account's email
# keybind: Vesha/switcher | / | Search accounts (n / N: next / previous match)
# keybind: Vesha/switcher | ? | Show all keys
# keybind: Vesha/switcher | q / Esc | Quit the switcher
# keybind: Vesha/sign-in | Enter | Send the code the sign-in page shows
# keybind: Vesha/sign-in | Ctrl+o | Open the sign-in page again
# keybind: Vesha/sign-in | Ctrl+y | Copy the sign-in link
# keybind: Vesha/sign-in | Esc | Cancel the sign-in

PALETTE = {  # Catppuccin Mocha, as curses colour numbers 16+
    "text": (205, 214, 244), "sub": (166, 173, 200), "dim": (127, 132, 156), "faint": (69, 71, 90),
    "peach": (250, 179, 135), "green": (166, 227, 161), "red": (243, 139, 168), "yellow": (249, 226, 175),
    "sky": (137, 220, 235), "mauve": (203, 166, 247), "lav": (180, 190, 254), "crust": (17, 17, 27),
    "selbg": (42, 43, 60), "surface": (49, 50, 68), "rose": (235, 160, 172), "border": (88, 91, 112),
}
FALLBACK = {"text": curses.COLOR_WHITE, "sub": curses.COLOR_WHITE, "dim": curses.COLOR_WHITE, "faint": curses.COLOR_BLACK,
            "peach": curses.COLOR_YELLOW, "green": curses.COLOR_GREEN, "red": curses.COLOR_RED, "yellow": curses.COLOR_YELLOW,
            "sky": curses.COLOR_CYAN, "mauve": curses.COLOR_MAGENTA, "lav": curses.COLOR_BLUE, "crust": curses.COLOR_BLACK,
            "selbg": curses.COLOR_BLACK, "surface": curses.COLOR_BLACK, "rose": curses.COLOR_RED,
            "border": curses.COLOR_WHITE}
HELP = [
    ("Move", [("j k", "down / up (3j: three)"), ("gg G", "first / last"), ("Ctrl-d Ctrl-u", "half a page"),
              ("1-9", "jump to that account"), ("h l", "accounts / folders tab"),
              ("Tab", "accounts ⇄ folders")]),
    ("Accounts", [("Enter s", "switch to it (active)"), ("r", "run claude as it, here"), ("p", "pause / resume auto"),
                  ("m", "this folder uses it"), ("a", "add (sign in)"), ("R cw", "rename"), ("dd", "remove"), ("y", "copy email")]),
    ("Sign in", [("Enter", "send the page's code"), ("Ctrl-o", "open the page again"), ("Ctrl-y", "copy the link"),
                           ("Esc", "cancel")]),
    ("Other", [("u", "refresh usage"), ("/ n N", "search, next, previous"), ("dd", "remove a folder rule (Folders)"),
               ("?", "this help"), ("q Esc", "quit")]),
]


class App:
    def __init__(self, scr):
        self.scr = scr
        self.st = core.load()
        self.use = {}
        self.loading = False
        self.focus = "accounts"
        self.sel = {"accounts": max(0, self.names().index(self.st["default"])) if self.st["default"] in self.names() else 0,
                    "folders": 0}
        self.pending = ""
        self.count = ""
        self.count_at = 0
        self.mode = "NORMAL"
        self.toast_msg, self.toast_at, self.toast_kind = "", 0, "ok"
        self.filter = ""
        self.input = None   # (prompt, buffer, callback)
        self.confirm = None   # (question, callback)
        self.help = False
        self.signin = None   # a core.SignIn while an account signs in
        self.code_buf = ""
        self.problems, self.running = {}, {}
        self.frame = 0
        self.cwd = os.getcwd()
        self.after = None   # an action to run after leaving curses
        self.lock = threading.Lock()
        self.init_colors()
        self.refresh_usage(fresh=False)

    # ---------------------------------------------------------------- data
    def names(self):
        return list(self.st["accounts"])

    def folders(self):
        return sorted(self.st["folders"].items())

    def current(self):
        n = self.names()
        return n[self.sel["accounts"]] if n and self.sel["accounts"] < len(n) else None

    def refresh_usage(self, fresh=True):
        if self.loading:
            return
        self.loading = True

        def work():
            try:
                u = core.usage(self.st, self.names(), fresh)
                with self.lock:
                    self.use = u
            finally:
                self.loading = False
                if fresh:
                    self.toast(f"usage refreshed for {len(self.names())} account(s)")
        threading.Thread(target=work, daemon=True).start()

    # ---------------------------------------------------------------- colours
    def init_colors(self):
        curses.start_color()
        try:
            curses.use_default_colors()
            bg = -1
        except curses.error:
            bg = curses.COLOR_BLACK
        self.cp = {}
        custom = curses.can_change_color() and curses.COLORS >= 256
        for i, (name, rgb) in enumerate(PALETTE.items()):
            num = 16 + i
            if custom:
                try:
                    curses.init_color(num, *(round(v * 1000 / 255) for v in rgb))
                except curses.error:
                    custom = False
            self.cp[name] = num if custom else FALLBACK[name]
        pairs = {}
        n = 1
        for fg in PALETTE:
            pairs[fg] = n
            curses.init_pair(n, self.cp[fg], bg)
            n += 1
        for fg in ("text", "peach", "sub", "dim", "green", "red", "sky", "lav", "yellow", "faint", "rose"):
            pairs["sel_" + fg] = n
            curses.init_pair(n, self.cp[fg], self.cp["selbg"])
            n += 1
        for name, fg, bgc in (("chip_peach", "crust", "peach"), ("chip_green", "crust", "green"), ("chip_sky", "crust", "sky"),
                              ("chip_dim", "text", "surface"), ("chip_red", "crust", "red"), ("chip_yellow", "crust", "yellow"),
                              ("key", "sub", "surface")):
            pairs[name] = n
            curses.init_pair(n, self.cp[fg], self.cp[bgc])
            n += 1
            pairs["cap_" + name] = n   # the rounded ends: the chip's colour on the background
            curses.init_pair(n, self.cp[bgc], bg)
            n += 1
        self.pairs = pairs

    def a(self, name, bold=False, sel=False):
        key = ("sel_" + name) if sel and ("sel_" + name) in self.pairs else name
        return curses.color_pair(self.pairs[key]) | (curses.A_BOLD if bold else 0)

    # ---------------------------------------------------------------- drawing
    def put(self, y, x, text, attr=0):
        h, w = self.scr.getmaxyx()
        if y < 0 or y >= h or x >= w:
            return x
        text = str(text)[: max(0, w - x)]
        try:
            self.scr.addstr(y, x, text, attr)
        except curses.error:
            pass   # writing the bottom-right cell moves the cursor off-screen: harmless
        return x + len(text)

    def box(self, y, x, h, w, title=(), right=()):
        """A rounded box like sangam's panes; title and right are [(text, colour)]."""
        if h < 2 or w < 4:
            return
        b = self.a("border")
        self.put(y, x, "╭" + "─" * (w - 2) + "╮", b)
        for i in range(1, h - 1):
            self.put(y + i, x, "│", b)
            self.put(y + i, x + w - 1, "│", b)
        self.put(y + h - 1, x, "╰" + "─" * (w - 2) + "╯", b)
        tx = x + 2
        if title:
            tx = self.put(y, tx, " ", b)
            for text, color in title:
                tx = self.put(y, tx, text, self.a(color, color in ("text", "rose", "yellow")))
            self.put(y, tx, " ", b)
        if right:
            width = sum(len(t) for t, _ in right) + 2
            rx = self.put(y, x + w - 2 - width, " ", b)
            for text, color in right:
                rx = self.put(y, rx, text, self.a(color, color in ("text", "rose", "yellow")))
            self.put(y, rx, " ", b)

    def wrap(self, y, x, w, text, attr):
        """Writes text word-wrapped to w columns; returns the next free row."""
        import textwrap
        for line in textwrap.wrap(text, max(10, w)) or [""]:
            self.put(y, x, line, attr)
            y += 1
        return y

    def section(self, y, x, w, title):
        """── title ────── inside a pane."""
        x2 = self.put(y, x, "── ", self.a("faint"))
        x2 = self.put(y, x2, title, self.a("dim"))
        self.put(y, x2 + 1, "─" * max(0, x + w - x2 - 2), self.a("faint"))

    def bar(self, y, x, pct, width, sel=False):
        """A thin line: the used part bold in green / yellow / red (to half a
        cell), the rest a faint hairline. No background, so it suits a
        transparent terminal and rows don't run together."""
        pct = max(0, min(100, pct))
        color = "red" if pct >= core.config()["warn_at"] else "yellow" if pct >= 50 else "green"   # used up: green → yellow → red
        halves = round(width * 2 * pct / 100)
        full, half = divmod(halves, 2)
        x = self.put(y, x, "━" * full, self.a(color, True, sel))
        if half:
            x = self.put(y, x, "╾", self.a(color, True, sel))   # heavy into light: no gap before the track
        self.put(y, x, "─" * (width - full - half), self.a("faint", sel=sel))
        return color

    def chip(self, y, x, text, kind, pair=None):
        """A rounded capsule, like the tmux bar's."""
        pair = pair or "chip_" + kind
        x = self.put(y, x, "\ue0b6", self.a("cap_" + pair))
        x = self.put(y, x, text, curses.color_pair(self.pairs[pair]) | curses.A_BOLD)
        return self.put(y, x, "\ue0b4", self.a("cap_" + pair)) + 1

    def draw(self):
        self.scr.erase()
        h, w = self.scr.getmaxyx()
        if h < 16 or w < 72:
            self.put(0, 0, "vesha needs a bigger window (72×16)", self.a("yellow", True))
            self.scr.refresh()
            return
        self.problems = core.login_problems(self.st)
        self.running = core.running_profiles()
        self.draw_tabs(w)
        top, bottom = 3, h - 2   # panes between the tab strip and the status line
        names = self.names()
        if w >= 120:
            lw = max(64, min(w * 62 // 100, w - 50))
            self.draw_list(top, 0, bottom - top + 1, lw)
            self.draw_side(top, lw + 1, bottom - top + 1, w - lw - 1)
        else:   # narrow: the list on top, the details under it
            lh = min(max(len(names) if self.focus == "accounts" else len(self.folders()), 1) + 4, (bottom - top + 1) // 2)
            self.draw_list(top, 0, lh, w)
            self.draw_side(top + lh, 0, bottom - top + 1 - lh, w)
        self.statusline()
        if self.help:
            self.draw_help()
        self.scr.refresh()

    def draw_tabs(self, w):
        here, why = core.resolve(self.st, self.cwd)
        self.box(0, 0, 3, w)
        x = self.put(1, 2, "vesha", self.a("rose", True))
        x = self.put(1, x + 1, "वेष", self.a("dim")) + 3
        for tab, n in (("accounts", len(self.names())), ("folders", len(self.folders()))):
            label = f"{tab.capitalize()}  {n}"
            if self.focus == tab and not self.signin:
                x = self.chip(1, x, label, "yellow") + 2
            else:
                x = self.put(1, x + 1, tab.capitalize(), self.a("sub"))
                x = self.put(1, x + 2, str(n), self.a("dim")) + 3
        if self.signin:
            x = self.chip(1, x, f"Sign in  {self.signin.name}", "green") + 2
        conf = core.config()
        right = [("new claude here → ", "dim"), (here or "–", "peach"), (f"  ({why})", "dim"),
                 ("   auto " + ("on" if conf["auto"] else "off"), "green" if conf["auto"] else "red"),
                 ("   ? keys", "dim")]
        width = sum(len(t) for t, _ in right)
        if width + x + 2 > w - 2:   # too narrow: keep what matters
            right = [(here or "–", "peach"), ("   ? keys", "dim")]
            width = sum(len(t) for t, _ in right)
        rx = w - 2 - width
        for text, color in right:
            rx = self.put(1, rx, text, self.a(color, color == "peach"))

    # ---- left pane: accounts or folder rules
    def draw_list(self, y, x, h, w):
        if self.focus == "folders":
            return self.draw_folders(y, x, h, w)
        names = self.names()
        spin = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"[self.frame % 10] + " checking usage" if self.loading else ""
        self.box(y, x, h, w, [("◉ ", "rose"), ("accounts", "rose"), (f" · active {self.st['default'] or '–'} · {len(names)}", "dim")],
                 [(spin, "dim")] if spin else ())
        if not names:
            self.put(y + 2, x + 3, "No accounts yet.", self.a("text", True))
            self.put(y + 3, x + 3, "a  sign one in   ·   or: vesha import cswap   ·   vesha add <name> --current", self.a("dim"))
            return
        inner = w - 4
        week = inner >= 64
        name_w = max(10, min(16, max(len(n) for n in names) + 1))
        use_w = 14   # a pill of 8, then " 100%"
        email_w = max(8, inner - 6 - name_w - 10 - use_w * (2 if week else 1) - 1)
        cx = {"i": x + 3, "name": x + 8, "email": x + 8 + name_w, "plan": x + 8 + name_w + email_w + 1}
        cx["h5"] = cx["plan"] + 10
        cx["wk"] = cx["h5"] + use_w + 1
        hy = y + 1
        for key, label in (("i", "#"), ("name", "account"), ("email", "email"), ("plan", "plan"), ("h5", "5 hours")) + \
                (("wk", "week"),) * week:
            self.put(hy, cx[key], label, self.a("dim"))
        self.put(hy + 1, x + 1, "─" * (w - 2), self.a("faint"))
        rows = h - 4
        top = max(0, self.sel["accounts"] - rows + 1)
        for row, n in enumerate(names[top: top + rows]):
            i = top + row
            ry = y + 3 + row
            acc = self.st["accounts"][n]
            sel = i == self.sel["accounts"]
            if sel:
                self.put(ry, x + 2, " " * (w - 4), self.a("text", sel=True))
                self.put(ry, x + 1, "▌", self.a("rose", True))
            hit = self.filter and self.filter.lower() in f"{n} {acc.get('email', '')}".lower()
            self.put(ry, cx["i"], str(i + 1) if i < 9 else " ", self.a("yellow" if not sel else "yellow", True, sel))
            mark, mcol = ("!", "red") if self.problems.get(n) else ("●", "peach") if n == self.st["default"] else \
                ("‖", "dim") if acc.get("paused") else (" ", "dim")
            self.put(ry, cx["name"] - 3, mark, self.a(mcol, True, sel))
            self.put(ry, cx["name"], n[: name_w - 1], self.a("yellow" if hit else "text", sel or n == self.st["default"], sel))
            email = acc.get("email") or "–"
            self.put(ry, cx["email"], email if len(email) < email_w else email[: email_w - 2] + "…", self.a("sub", sel=sel))
            self.put(ry, cx["plan"], (acc.get("plan") or "–")[:9], self.a("dim", sel=sel))
            u = self.use.get(n)
            if isinstance(u, dict):
                for key in ("five_hour", "seven_day")[: 2 if week else 1]:
                    if key in u:
                        col = cx["h5" if key == "five_hour" else "wk"]
                        p = u[key]["pct"]
                        color = self.bar(ry, col, p, 8, sel)
                        self.put(ry, col + 9, f"{p:>3}%", self.a(color, True, sel))
            elif u is not None:
                self.put(ry, cx["h5"], ("no login" if "sign" in str(u) or "login" in str(u) else "couldn't check")[: use_w * 2],
                         self.a("yellow", sel=sel))
            else:
                self.put(ry, cx["h5"], "…", self.a("faint", sel=sel))

    def draw_folders(self, y, x, h, w):
        rules = self.folders()
        self.box(y, x, h, w, [("◉ ", "rose"), ("folder rules", "rose"), (f" · {len(rules)}", "dim")])
        if not rules:
            self.put(y + 2, x + 3, "No folder rules: every folder uses the active account.", self.a("dim"))
            self.put(y + 3, x + 3, "m on an account makes this folder always use it.", self.a("faint"))
            return
        self.put(y + 1, x + 3, "folder (and everything under it)", self.a("dim"))
        self.put(y + 1, x + w - 18, "account", self.a("dim"))
        self.put(y + 2, x + 1, "─" * (w - 2), self.a("faint"))
        for i, (f, n) in enumerate(rules[: h - 4]):
            ry = y + 3 + i
            sel = i == self.sel["folders"]
            if sel:
                self.put(ry, x + 2, " " * (w - 4), self.a("text", sel=True))
                self.put(ry, x + 1, "▌", self.a("rose", True))
            f = "~" + f[len(core.HOME):] if f == core.HOME or f.startswith(core.HOME + "/") else f
            self.put(ry, x + 3, f[: w - 24], self.a("sky", sel=sel))
            self.put(ry, x + w - 18, n, self.a("text", True, sel))

    # ---- right pane: the selected account, or the sign-in
    def draw_side(self, y, x, h, w):
        if self.signin:
            return self.draw_signin(y, x, h, w)
        n = self.current() if self.focus == "accounts" else (self.folders()[self.sel["folders"]][1] if self.folders() else None)
        if not n or n not in self.st["accounts"]:
            self.box(y, x, h, w)
            return
        acc = self.st["accounts"][n]
        self.box(y, x, h, w, [(n, "rose"), (" · overview", "dim")])
        lx, iw = x + 2, w - 4
        cy = y + 1
        cx = self.put(cy, lx, n, self.a("text", True)) + 2
        live = self.running.get(os.path.realpath(core.profile_dir(self.st, n)), 0)
        for show, label, kind in ((n == self.st["default"], "ACTIVE", "peach"), (acc.get("paused"), "PAUSED", "dim"),
                                  (self.problems.get(n), "LOGIN CHANGED", "red"), (live, f"{live} RUNNING", "green")):
            if show:
                cx = self.chip(cy, cx, label, kind) + 1
        cy += 1
        self.put(cy, lx, " · ".join(v for v in (acc.get("email"), acc.get("plan"), acc.get("org")) if v)[:iw], self.a("sub"))
        cy += 1
        for p in self.problems.get(n, [])[:2]:
            self.put(cy, lx, ("! " + p)[:iw], self.a("red", True))
            cy += 1
        if cy < y + h - 2:
            cy += 1
            self.section(cy, lx, iw, "usage")
            cy += 1
            u = self.use.get(n)
            if isinstance(u, dict):
                bw = max(10, min(24, iw - 36))
                for key, label in (("five_hour", "5 hours"), ("seven_day", "week")):
                    if key in u:
                        p = u[key]["pct"]
                        rel, clock = core.resets_in(u[key].get("resets_at"))
                        self.put(cy, lx, label, self.a("dim"))
                        color = self.bar(cy, lx + 9, p, bw)
                        ex = self.put(cy, lx + 10 + bw, f"{p:>3}%", self.a(color, True))
                        reset = f"↻ {clock}" if clock else ""   # when it resets: today 9:40 PM, Sat 6:00 AM
                        self.put(cy, ex + 2, reset[: max(0, lx + iw - ex - 2)], self.a("dim"))
                        cy += 1
                if u.get("stale"):
                    self.put(cy, lx, "last known numbers", self.a("faint"))
                    cy += 1
            else:
                self.put(cy, lx, str(u) if u is not None else "checking…", self.a("yellow" if u is not None else "faint"))
                cy += 1
        d = core.profile_dir(self.st, n)
        who = core.identity(d)
        exp = who["login_expires"]
        login = ("✓ signed in" + (f" · good for {int((exp - time.time()) / 86400)} more days" if exp else "")) \
            if who["signed_in"] else f"✗ signed out: vesha login {n}"
        folders = [f.replace(core.HOME, "~", 1) for f, m in self.folders() if m == n]
        facts = [("login", login, "green" if who["signed_in"] else "red"),
                 ("profile", d.replace(core.HOME, "~") + ("  (Claude Code's own)" if d == core.MAIN_DIR else ""), "sub"),
                 ("folders", ", ".join(folders) or "none: follows the active account", "sky" if folders else "dim")]
        if cy + 5 < y + h - 1:
            cy += 1
            self.section(cy, lx, iw, "account")
            cy += 1
            for k, v, color in facts:
                self.put(cy, lx, k, self.a("dim"))
                self.put(cy, lx + 9, v[: iw - 9], self.a(color))
                cy += 1
        what = [("Enter", "switch to it" if n != self.st["default"] else "(already active)"), ("r", "run claude as it, here"),
                ("p", "resume" if acc.get("paused") else "pause (no auto-switching to it)"), ("m", "this folder always uses it"),
                ("R", "rename"), ("dd", "remove")]
        if self.problems.get(n):
            what.insert(0, ("", "fix: quit and run vesha repair"))
        if cy + len(what) + 2 < y + h - 1:
            cy += 1
            self.section(cy, lx, iw, "what now")
            cy += 1
            for k, d2 in what:
                self.put(cy, lx, k, self.a("rose", True))
                self.put(cy, lx + 7, d2[: iw - 7], self.a("text" if k else "red"))
                cy += 1

    def draw_signin(self, y, x, h, w):
        si = self.signin
        self.box(y, x, h, w, [("sign in", "rose"), (f" · {si.name}", "dim")])
        lx, iw = x + 2, w - 4
        cy = y + 1
        cx = self.put(cy, lx, "Sign in", self.a("rose", True))
        self.put(cy, cx + 2, si.name, self.a("text", True))
        cy += 1
        cy = self.wrap(cy + 0, lx, iw, (f"as {si.email}, " if si.email else "") + "on Anthropic's sign-in page in your browser",
                       self.a("sub")) + 1
        self.section(cy, lx, iw, "steps")
        cy += 1
        spin = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"[self.frame % 10]
        steps = [(bool(si.url), "a tab opened in your browser" + (" (email filled in)" if si.email else "")),
                 (si.code_sent, "there, enter your email and the code Anthropic emails you"),
                 (si.code_sent, "if the page then shows a code, paste it below and press Enter"),
                 (si.done, "vesha adds the account")]
        current = next((i for i, (ok, _) in enumerate(steps) if not ok), len(steps))
        for i, (ok, text) in enumerate(steps):
            mark, color = ("✓", "green") if ok else (spin, "peach") if i == current else ("·", "faint")
            self.put(cy, lx, mark, self.a(color, True))
            cy = self.wrap(cy, lx + 2, iw - 2, text, self.a("text" if i <= current else "dim"))
        cy += 1
        self.section(cy, lx, iw, "code from the page (optional)")
        cy += 1
        bx = self.put(cy, lx, "❯ ", self.a("rose", True))
        bx = self.put(cy, bx, self.code_buf[-(iw - 4):], self.a("text", True))
        self.put(cy, bx, "▏", self.a("peach", True))
        cy += 2
        self.section(cy, lx, iw, "what now")
        cy += 1
        for k, d in (("Enter", "send the pasted code"), ("Ctrl+o", "open the sign-in page again"),
                     ("Ctrl+y", "copy the sign-in link"), ("Esc", "cancel")):
            if cy >= y + h - 2:
                break
            self.put(cy, lx, k, self.a("rose", True))
            self.put(cy, lx + 8, d, self.a("text"))
            cy += 1
        last = si.last_line()
        if last and y + h - 2 > cy:
            self.put(y + h - 2, lx, ("claude: " + last)[:iw], self.a("faint"))

    def statusline(self):
        h, w = self.scr.getmaxyx()
        y = h - 1
        mode_kind = {"NORMAL": "peach", "FILTER": "sky", "CONFIRM": "red", "RENAME": "yellow", "ADD": "green",
                     "SIGN IN": "green"}[self.mode]
        x = self.chip(y, 1, self.mode, mode_kind)
        if self.input:
            prompt, buf, _ = self.input
            x = self.put(y, x + 1, prompt, self.a("dim"))
            x = self.put(y, x, buf, self.a("text", True))
            self.put(y, x, "▏", self.a("peach", True))
            return
        if self.confirm:
            self.put(y, x + 1, self.confirm[0] + "  y / n", self.a("text", True))
            return
        if self.pending or self.count:
            x = self.put(y, x + 1, self.count + self.pending, self.a("text", True))
        if self.toast_msg and time.time() - self.toast_at < 3.5:
            self.put(y, x + 2, self.toast_msg, self.a({"ok": "green", "warn": "yellow", "err": "red"}[self.toast_kind]))
            return
        if self.signin:
            hints = [("Enter", "send code"), ("Ctrl+o", "open page"), ("Ctrl+y", "copy link"), ("Esc", "cancel")]
        elif self.focus == "accounts":
            hints = [("Enter", "switch"), ("r", "run here"), ("u", "usage"), ("p", "pause"), ("m", "map folder"),
                     ("a", "add"), ("dd", "remove")]
        else:
            hints = [("dd", "remove rule"), ("Tab", "accounts")]
        if not self.signin:
            hints += [("?", "keys"), ("q", "quit")]
        hx = x + 2
        for k, label in hints:
            if hx + len(k) + len(label) + 4 > w - 2:
                break
            hx = self.chip(y, hx, k, None, "key")
            hx = self.put(y, hx, label, self.a("dim")) + 2

    def draw_help(self):
        """The keys, in as many columns as the terminal fits (3, 2 or 1)."""
        h, w = self.scr.getmaxyx()
        key_w = max(len(k) for _, rows in HELP for k, _ in rows) + 2
        desc_w = max(len(d) for _, rows in HELP for _, d in rows) + 2
        col_w = key_w + desc_w
        ncols = max(1, min(len(HELP), (w - 8) // col_w))
        groups = [HELP[i::ncols] for i in range(ncols)]   # spread the groups over the columns
        col_h = max(sum(len(rows) + 2 for _, rows in g) for g in groups)
        bw, bh = min(w - 2, ncols * col_w + 4), min(h - 2, col_h + 5)
        y0, x0 = max(1, (h - bh) // 2), max(1, (w - bw) // 2)
        for i in range(bh):
            self.put(y0 + i, x0, " " * bw, self.a("text", sel=True))
        self.put(y0, x0 + 2, " Keys ", self.a("chip_peach", True))
        for ci, g in enumerate(groups):
            cx, cy = x0 + 2 + ci * col_w, y0 + 2
            for title, rows in g:
                self.put(cy, cx, title.upper(), self.a("peach", True, True))
                cy += 1
                for k, d in rows:
                    if cy >= y0 + bh - 2:
                        break
                    self.put(cy, cx, k, self.a("sky", True, True))
                    self.put(cy, cx + key_w, d, self.a("sub", sel=True))
                    cy += 1
                cy += 1
        self.put(y0 + bh - 2, x0 + 2, "? or Esc closes this · vesha help lists every command", self.a("dim", sel=True))

    def toast(self, msg, kind="ok"):
        self.toast_msg, self.toast_at, self.toast_kind = msg, time.time(), kind

    # ---------------------------------------------------------------- actions
    def save_reload(self):
        core.save(self.st)
        self.st = core.load()

    def act_switch(self):
        n = self.current()
        if not n:
            return
        if n == self.st["default"]:
            self.toast(f"{n} is already the active account", "warn")
            return
        try:
            core.activate(self.st, n)
        except core.VeshaError as e:
            self.toast(str(e), "err")
            return
        self.st = core.load()
        core.signal_bar()
        self.toast(f"✓ {n} is active: running claude sessions use it from their next message, new ones too")

    def act_pause(self):
        n = self.current()
        if n:
            acc = self.st["accounts"][n]
            acc["paused"] = not acc.get("paused")
            self.save_reload()
            self.toast(f"{n} " + ("won't be picked by auto-switching" if self.st["accounts"][n]["paused"] else "can be picked again"))

    def act_map(self):
        n = self.current()
        if n:
            try:
                f = core.map_folder(self.st, n, self.cwd)
                self.st = core.load()
                self.toast(f"✓ {f.replace(core.HOME, '~')} and below always use {n}")
            except core.VeshaError as e:
                self.toast(str(e), "err")

    def act_copy(self):
        n = self.current()
        email = self.st["accounts"].get(n, {}).get("email") if n else None
        if not email:
            return
        try:
            subprocess.run(["wl-copy"], input=email, text=True, timeout=3)
            self.toast(f"copied {email}")
        except (OSError, subprocess.TimeoutExpired):
            self.toast("couldn't copy (no wl-copy)", "err")

    def act_remove(self):
        if self.focus == "folders":
            rules = self.folders()
            if not rules:
                return
            f, n = rules[self.sel["folders"]]

            def do():
                core.unmap_folder(self.st, f)
                self.st = core.load()
                self.sel["folders"] = max(0, min(self.sel["folders"], len(self.folders()) - 1))
                self.toast(f"✓ {f} follows the active account again")
            self.ask(f"Remove the rule {f} → {n}?", do)
            return
        n = self.current()
        if not n:
            return
        what = "forget it (the login stays in ~/.claude)" if self.st["accounts"][n].get("main") else "delete its profile and login"

        def do():
            core.remove(self.st, n)
            self.st = core.load()
            self.sel["accounts"] = max(0, min(self.sel["accounts"], len(self.names()) - 1))
            self.toast(f"✓ removed {n}")
        self.ask(f"Remove {n}? This will {what}.", do)

    def act_rename(self):
        n = self.current()
        if not n:
            return

        def done(new):
            try:
                core.rename(self.st, n, new.strip())
                self.st = core.load()
                self.toast(f"✓ {n} is now {new.strip()}")
            except core.VeshaError as e:
                self.toast(str(e), "err")
        self.prompt("RENAME", f"rename {n} to: ", n, done)

    def act_add(self):
        def got_email(name, email):
            email = email.strip()
            if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
                self.toast(f"“{email}” isn't an email address", "err")
                return
            try:
                self.signin = core.SignIn(self.st, name, email)
            except core.VeshaError as e:
                self.toast(str(e), "err")
                return
            self.code_buf, self.mode = "", "SIGN IN"

        def got_name(name):
            name = name.strip()
            try:
                core.check_name(name)
                if name in self.st["accounts"]:
                    raise core.VeshaError(f"there's already an account called {name}")
            except core.VeshaError as e:
                self.toast(str(e), "err")
                return
            self.prompt("ADD", f"{name}'s email (Enter to type it in the browser instead): ", "", lambda e: got_email(name, e))
        self.prompt("ADD", "name for the new account (e.g. work, client-x): ", "", got_name)

    def signin_key(self, ch):
        si = self.signin
        if ch == 27:
            si.cancel()
            self.signin, self.mode = None, "NORMAL"
            self.toast("sign-in cancelled", "warn")
        elif ch in (10, 13):
            if self.code_buf.strip():
                si.send_code(self.code_buf)
                self.code_buf = ""
        elif ch == 15:   # Ctrl-o
            if si.url:
                subprocess.Popen(["xdg-open", si.url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.toast("opened the sign-in page")
        elif ch == 25:   # Ctrl-y
            if si.url:
                try:
                    subprocess.run(["wl-copy"], input=si.url, text=True, timeout=3)
                    self.toast("copied the sign-in link")
                except (OSError, subprocess.TimeoutExpired):
                    self.toast("couldn't copy (no wl-copy)", "err")
        elif ch in (curses.KEY_BACKSPACE, 127, 8):
            self.code_buf = self.code_buf[:-1]
        elif ch == 21:   # Ctrl-u
            self.code_buf = ""
        elif 32 <= ch < 0x110000:
            self.code_buf += chr(ch)
        return True

    def signin_poll(self):
        si = self.signin
        if not si or not si.done:
            return
        self.signin, self.mode = None, "NORMAL"
        try:
            who = si.finish(self.st)
        except core.VeshaError as e:
            self.toast(f"✗ {si.name} wasn't added: {e}", "err")
            return
        self.st = core.load()
        self.focus = "accounts"
        if si.name in self.names():
            self.sel["accounts"] = self.names().index(si.name)
        self.toast(f"✓ {si.name} signed in ({who['email']}, {who['plan']}): Enter makes it active")
        self.refresh_usage(True)

    def ask(self, question, cb):
        self.mode = "CONFIRM"
        self.confirm = (question, cb)

    def prompt(self, mode, text, initial, cb):
        self.mode = mode
        self.input = (text, initial, cb)

    # ---------------------------------------------------------------- keys
    def move(self, delta):
        size = len(self.names()) if self.focus == "accounts" else len(self.folders())
        if size:
            self.sel[self.focus] = max(0, min(size - 1, self.sel[self.focus] + delta))

    def key(self, ch):
        if self.signin and not self.input:
            return self.signin_key(ch)
        if self.help:
            if ch in (ord("?"), 27, ord("q")):
                self.help = False
            return True
        if self.confirm:
            question, cb = self.confirm
            self.confirm, self.mode = None, "NORMAL"
            if ch in (ord("y"), ord("Y"), 10, 13):
                try:
                    cb()
                except core.VeshaError as e:
                    self.toast(str(e), "err")
            else:
                self.toast("cancelled", "warn")
            return True
        if self.input:
            text, buf, cb = self.input
            if ch == 27:
                self.input, self.mode = None, "NORMAL"
                if self.filter and text.startswith("/"):
                    self.filter = ""
            elif ch in (10, 13):
                self.input, self.mode = None, "NORMAL"
                cb(buf)
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                self.input = (text, buf[:-1], cb)
            elif ch == 21:   # Ctrl-u clears
                self.input = (text, "", cb)
            elif 32 <= ch < 0x110000:
                self.input = (text, buf + chr(ch), cb)
            if self.input and text.startswith("/"):
                self.filter = self.input[1]
                self.jump_match(0)
            return True
        k = chr(ch) if 0 < ch < 0x110000 else ""
        if k.isdigit() and (k != "0" or self.count) and not self.pending:
            self.count += k
            self.count_at = time.time()
            return True
        n = int(self.count or 1)
        had = bool(self.count)
        self.count = ""
        if self.pending:
            combo, self.pending = self.pending + k, ""
            if combo == "gg":
                self.sel[self.focus] = 0
            elif combo == "dd":
                self.act_remove()
            elif combo == "cw":
                self.act_rename()
            return True
        if k in ("g", "d", "c"):
            self.pending = k
            return True
        if had and k not in ("j", "k", "G") and ch not in (curses.KEY_DOWN, curses.KEY_UP) and self.focus == "accounts":
            self.jump_to(n)   # "2 Enter": jump to account 2, then the key acts on it
        if k == "j" or ch == curses.KEY_DOWN:
            self.move(n)
        elif k == "k" or ch == curses.KEY_UP:
            self.move(-n)
        elif k == "G":
            size = len(self.names()) if self.focus == "accounts" else len(self.folders())
            self.sel[self.focus] = (n - 1 if had else size - 1) if size else 0
            self.sel[self.focus] = max(0, min(self.sel[self.focus], size - 1))
        elif ch == 4:    # Ctrl-d
            self.move(max(1, (self.scr.getmaxyx()[0] - 16) // 2))
        elif ch == 21:   # Ctrl-u
            self.move(-max(1, (self.scr.getmaxyx()[0] - 16) // 2))
        elif ch == 9:    # Tab
            self.focus = "folders" if self.focus == "accounts" else "accounts"
        elif k == "l" or ch == curses.KEY_RIGHT:
            self.focus = "folders"
        elif k == "h" or ch == curses.KEY_LEFT:
            self.focus = "accounts"
        elif self.focus == "accounts" and (ch in (10, 13) or k == "s"):
            self.act_switch()
        elif self.focus == "accounts" and k == "r":
            if self.current():
                self.after = ("run", self.current())
                return False
        elif k == "u":
            self.refresh_usage(True)
            self.toast("asking Anthropic for usage…")
        elif self.focus == "accounts" and k == "p":
            self.act_pause()
        elif self.focus == "accounts" and k == "m":
            self.act_map()
        elif k == "a":
            self.act_add()
        elif self.focus == "accounts" and k == "R":
            self.act_rename()
        elif self.focus == "accounts" and k == "y":
            self.act_copy()
        elif k == "/":
            self.filter = ""
            self.prompt("FILTER", "/", "", lambda s: self.jump_match(0) if s else None)
        elif k in ("n", "N"):
            self.jump_match(1 if k == "n" else -1)
        elif k == "?":
            self.help = True
        elif k == "q" or ch == 27:
            return False
        return True

    def jump_to(self, n):
        names = self.names()
        if 1 <= n <= len(names):
            self.sel["accounts"] = n - 1
            self.focus = "accounts"

    def jump_match(self, step):
        if not self.filter:
            return
        names = self.names()
        hits = [i for i, n in enumerate(names) if self.filter.lower() in f"{n} {self.st['accounts'][n].get('email', '')}".lower()]
        if not hits:
            self.toast(f"no account matches “{self.filter}”", "warn")
            return
        cur = self.sel["accounts"]
        if step == 0:
            nxt = next((i for i in hits if i >= cur), hits[0])
        elif step > 0:
            nxt = next((i for i in hits if i > cur), hits[0])
        else:
            nxt = next((i for i in reversed(hits) if i < cur), hits[-1])
        self.focus = "accounts"
        self.sel["accounts"] = nxt

    def loop(self):
        curses.curs_set(0)
        self.scr.timeout(100)
        self.scr.keypad(True)
        curses.set_escdelay(25)
        while True:
            self.frame += 1
            if self.count and time.time() - self.count_at > 0.6:   # a lone number: jump to that account
                self.jump_to(int(self.count))
                self.count = ""
            self.signin_poll()
            self.draw()
            try:
                ch = self.scr.get_wch()
            except curses.error:
                continue
            except KeyboardInterrupt:
                return
            code = ord(ch) if isinstance(ch, str) else ch
            if code == curses.KEY_RESIZE:
                continue
            if not self.key(code):
                return
            if self.after:
                return


def run():
    while True:
        holder = {}

        def main(scr, holder=holder):
            app = App(scr)
            holder["app"] = app
            app.loop()
        try:
            curses.wrapper(main)
        except KeyboardInterrupt:
            return 130
        app = holder.get("app")
        if not app or not app.after:
            return 0
        what, arg = app.after
        if what == "run":
            from .cli import exec_claude
            exec_claude([], arg)   # replaces this process
