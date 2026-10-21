"""The full-screen switcher (`vesha` with no arguments). Vim keys:

  j k ↓ ↑   move        gg G   top, bottom     Ctrl-d Ctrl-u  half a page
  1-9       jump to that account               Tab  accounts ⇄ folder rules
  Enter s   make it the active account         r    run claude as it, here
  u         refresh usage                      p    pause / resume (auto-switching)
  m         this folder always uses it         a    add an account
  R cw      rename                             dd   remove (asks)
  y         copy the email                     /    filter, n N next / previous
  ?         all keys                           q Esc quit
"""
import curses
import os
import subprocess
import threading
import time

from . import core

# keybind: Vesha/switcher | j / k | Move down / up an account (counts work: 3j)
# keybind: Vesha/switcher | gg / G | Jump to the first / last account
# keybind: Vesha/switcher | Ctrl+d / Ctrl+u | Scroll half a page down / up
# keybind: Vesha/switcher | 1-9 | Jump to that account
# keybind: Vesha/switcher | Tab | Switch between accounts and folder rules
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

PALETTE = {  # Catppuccin Mocha, as curses colour numbers 16+
    "text": (205, 214, 244), "sub": (166, 173, 200), "dim": (127, 132, 156), "faint": (69, 71, 90),
    "peach": (250, 179, 135), "green": (166, 227, 161), "red": (243, 139, 168), "yellow": (249, 226, 175),
    "sky": (137, 220, 235), "mauve": (203, 166, 247), "lav": (180, 190, 254), "crust": (17, 17, 27),
    "selbg": (60, 48, 50), "surface": (49, 50, 68),
}
FALLBACK = {"text": curses.COLOR_WHITE, "sub": curses.COLOR_WHITE, "dim": curses.COLOR_WHITE, "faint": curses.COLOR_BLACK,
            "peach": curses.COLOR_YELLOW, "green": curses.COLOR_GREEN, "red": curses.COLOR_RED, "yellow": curses.COLOR_YELLOW,
            "sky": curses.COLOR_CYAN, "mauve": curses.COLOR_MAGENTA, "lav": curses.COLOR_BLUE, "crust": curses.COLOR_BLACK,
            "selbg": curses.COLOR_BLACK, "surface": curses.COLOR_BLACK}
HELP = [
    ("Move", [("j k", "down / up (3j: three)"), ("gg G", "first / last"), ("Ctrl-d Ctrl-u", "half a page"),
              ("1-9", "jump to that account"), ("Tab", "accounts ⇄ folders")]),
    ("Accounts", [("Enter s", "switch to it (active)"), ("r", "run claude as it, here"), ("p", "pause / resume auto"),
                  ("m", "this folder uses it"), ("a", "add (sign in)"), ("R cw", "rename"), ("dd", "remove"), ("y", "copy email")]),
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
        for fg in ("text", "peach", "sub", "dim", "green", "red", "sky", "lav", "yellow", "faint"):
            pairs["sel_" + fg] = n
            curses.init_pair(n, self.cp[fg], self.cp["selbg"])
            n += 1
        for name, fg, bgc in (("chip_peach", "crust", "peach"), ("chip_green", "crust", "green"), ("chip_sky", "crust", "sky"),
                              ("chip_dim", "text", "surface"), ("chip_red", "crust", "red"), ("chip_yellow", "crust", "yellow"),
                              ("key", "sub", "surface")):
            pairs[name] = n
            curses.init_pair(n, self.cp[fg], self.cp[bgc])
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
        text = str(text)[: max(0, w - x - 1)]
        try:
            self.scr.addstr(y, x, text, attr)
        except curses.error:
            pass
        return x + len(text)

    def rule(self, y, title, right=""):
        h, w = self.scr.getmaxyx()
        x = self.put(y, 1, "━━ ", self.a("peach"))
        x = self.put(y, x, title, self.a("text", True))
        line_end = w - 3 - len(right)
        self.put(y, x + 1, "─" * max(0, line_end - x - 2), self.a("faint"))
        if right:
            self.put(y, w - 2 - len(right), right, self.a("dim"))

    def bar(self, y, x, pct, width, sel):
        pct = max(0, min(100, pct))
        fill = round(width * pct / 100)
        color = "red" if pct >= core.config()["warn_at"] else "peach" if pct >= 60 else "green"
        self.put(y, x, "━" * fill, self.a(color, sel=sel))
        self.put(y, x + fill, "━" * (width - fill), self.a("faint", sel=sel))
        return color

    def chip(self, y, x, text, kind):
        return self.put(y, x, f" {text} ", self.a("chip_" + kind, True)) + 1

    def draw(self):
        self.scr.erase()
        h, w = self.scr.getmaxyx()
        if h < 14 or w < 70:
            self.put(0, 0, "vesha needs a bigger window (70×14)", self.a("yellow", True))
            self.scr.refresh()
            return
        here, why = core.resolve(self.st, self.cwd)
        # header
        x = self.put(0, 1, "❯ ", self.a("peach", True))
        x = self.put(0, x, "vesha", self.a("text", True))
        x = self.put(0, x + 1, "वेष", self.a("peach"))
        right = f"new claude here → {here or '–'}  ({why})"
        if x + 24 < w - len(right) - 2:
            self.put(0, x + 2, "Claude Code accounts", self.a("dim"))
        self.put(0, w - len(right) - 2, "new claude here → ", self.a("dim"))
        self.put(0, w - len(right) - 2 + 18, here or "–", self.a("peach", True))
        self.put(0, w - len(right) - 2 + 18 + len(here or "–"), f"  ({why})", self.a("dim"))
        spin = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"[self.frame % 10] + " checking usage" if self.loading else ""
        names = self.names()
        self.rule(2, "Accounts", spin or f"{len(names)} account{'s' if len(names) != 1 else ''}")
        y = 3
        running = core.running_profiles()
        list_h = max(3, min(len(names), h - 16))
        top = max(0, self.sel["accounts"] - list_h + 1)
        if not names:
            self.put(y + 1, 4, "No accounts yet.", self.a("text", True))
            hint = "a  add one (sign in)   ·   or quit and run: vesha import cswap  /  vesha add <name> --current"
            self.put(y + 2, 4, hint, self.a("dim"))
        name_w = max(14, max([len(x) for x in names] + [0]) + 2)
        infos = {n: f"{self.st['accounts'][n].get('email') or '–'} · {self.st['accounts'][n].get('plan') or '–'}" for n in names}
        info_w = max([len(x) for x in infos.values()] + [10])
        problems = core.login_problems(self.st)
        rows = []
        for n in names[top: top + list_h]:
            acc = self.st["accounts"][n]
            tags = [("login changed", "red")] if problems.get(n) else []
            if n == self.st["default"]:
                tags.append(("active", "peach"))
            if n == here and n != self.st["default"]:
                tags.append(("here", "sky"))
            if acc.get("paused"):
                tags.append(("paused", "dim"))
            live = running.get(os.path.realpath(core.profile_dir(self.st, n)), 0)
            if live:
                tags.append((f"{live} running", "green"))
            rows.append(tags)
        # one tag column for every row, so the bars line up; the bars share what's left
        tags_x = w - 3 - max([sum(len(t) + 3 for t, _ in tags) for tags in rows] + [0])
        # the info column gives way (down to 18 wide) before the weekly bar does
        info_w = max(min(info_w, 18), min(info_w, tags_x - 9 - name_w - 2 - 2 * (17 + 6)))
        col_use = 9 + name_w + info_w + 2
        if tags_x - col_use < 23:   # narrow: the info column shrinks, then hides, before anything overlaps
            info_w -= 23 - (tags_x - col_use)
            info_w = info_w if info_w >= 8 else -2
            col_use = 9 + name_w + info_w + 2
        room = tags_x - col_use
        windows = 2 if (room - 34) // 2 >= 6 else 1   # the 5-hour window first: it matters most
        bw = max(6, min(18, (room - 17 * windows) // windows))
        for i, n in enumerate(names[top: top + list_h], start=top):
            acc = self.st["accounts"][n]
            sel = self.focus == "accounts" and i == self.sel["accounts"]
            if sel:
                self.put(y, 1, " " * (w - 3), self.a("text", sel=True))
            hit = self.filter and self.filter.lower() in f"{n} {acc.get('email', '')}".lower()
            self.put(y, 2, "❯" if sel else (str(i + 1) if i < 9 else " "), self.a("peach" if sel else "faint", True, sel))
            self.put(y, 4, f" {n[0].upper()} ", self.a("chip_" + ("peach" if n == self.st["default"] else "dim"), True))
            self.put(y, 9, n, self.a("yellow" if hit else "text", True, sel))
            info = infos[n]
            if info_w > 0:
                self.put(y, 9 + name_w, info if len(info) <= info_w else info[: info_w - 1] + "…", self.a("dim", sel=sel))
            tags = rows[i - top]
            u = self.use.get(n)
            ux = col_use
            if isinstance(u, dict):
                for key, label in (("five_hour", "5h"), ("seven_day", "wk"))[:windows]:
                    if key in u:
                        p = u[key]["pct"]
                        rel, _ = core.resets_in(u[key].get("resets_at"))
                        self.put(y, ux, label, self.a("dim", sel=sel))
                        color = self.bar(y, ux + 3, p, bw, sel)
                        self.put(y, ux + 4 + bw, f"{p:>3}%", self.a(color, True, sel))
                        self.put(y, ux + 9 + bw, rel[:7], self.a("dim", sel=sel))
                    ux += bw + 18
            elif u is not None:
                self.put(y, ux, str(u)[:40], self.a("yellow", sel=sel))
            else:
                self.put(y, ux, "…", self.a("faint"))
            tx = w - 2
            for t, k in reversed(tags):
                tx -= len(t) + 3
                self.chip(y, tx, t, k)
            y += 1
        # details of the selected account
        y += 1
        cur = self.current()
        if cur:
            acc = self.st["accounts"][cur]
            d = core.profile_dir(self.st, cur)
            who = core.identity(d)
            exp = who["login_expires"]
            login = "signed in" if who["signed_in"] else "signed out: a to sign in again"
            if who["signed_in"] and exp:
                days = int((exp - time.time()) / 86400)
                login += f" · login good for {days} more day{'s' if days != 1 else ''}"
            folders = [f.replace(core.HOME, "~", 1) for f, n in self.folders() if n == cur]
            for i, p in enumerate(problems.get(cur, [])[:2]):
                self.put(y + i, 3, ("! " + p + " (vesha repair)")[: w - 6], self.a("red", True))
            y += len(problems.get(cur, [])[:2]) + (1 if problems.get(cur) else 0)
            facts = [("account", " · ".join(x for x in (acc.get("email"), acc.get("plan"), acc.get("org")) if x) or "–", "sub"),
                     ("login", login, "green" if who["signed_in"] else "red"),
                     ("profile", d.replace(core.HOME, "~") + ("  (Claude Code's own)" if d == core.MAIN_DIR else ""), "sub"),
                     ("folders", ", ".join(folders) or "none (follows the active account)", "sky" if folders else "dim")]
            two = w >= 140
            for i, (k, v, color) in enumerate(facts):
                fy = y + (i // 2 if two else i)
                fx = (3 if i % 2 == 0 else w // 2) if two else 3
                self.put(fy, fx, k + " ", self.a("dim"))
                self.put(fy, fx + len(k) + 1, v[: (w // 2 - fx - len(k) - 3) if two and i % 2 == 0 else w], self.a(color))
            y += 1 if two else 3
            u = self.use.get(cur)
            if isinstance(u, dict) and "five_hour" in u:
                rel5, c5 = core.resets_in(u["five_hour"].get("resets_at"))
                relw, cw = core.resets_in(u.get("seven_day", {}).get("resets_at"))
                txt = f"5-hour resets {c5} (in {rel5})" + (f"   ·   week resets {cw} (in {relw})" if relw else "")
                self.put(y + 2, 3, "resets ", self.a("dim"))
                self.put(y + 2, 10, txt + ("   (last known numbers)" if u.get("stale") else ""), self.a("sub"))
        # folder rules
        y += 4
        conf = core.config()
        auto = f"auto-switch {'on' if conf['auto'] else 'off'} at {conf['switch_at']}%"
        self.rule(y, "Folders", auto)
        y += 1
        rules = self.folders()
        if not rules:
            self.put(y, 3, "No folder rules: every folder uses the active account.", self.a("dim"))
            self.put(y + 1, 3, "m on an account makes this folder always use it.", self.a("faint"))
        for i, (f, n) in enumerate(rules[: max(1, h - y - 3)]):
            sel = self.focus == "folders" and i == self.sel["folders"]
            if sel:
                self.put(y, 1, " " * (w - 3), self.a("text", sel=True))
            self.put(y, 2, "❯" if sel else " ", self.a("peach", True, sel))
            f = "~" + f[len(core.HOME):] if f == core.HOME or f.startswith(core.HOME + "/") else f
            self.put(y, 4, f, self.a("sky", sel=sel))
            self.put(y, max(36, len(f) + 6), "→ ", self.a("dim", sel=sel))
            self.put(y, max(38, len(f) + 8), n, self.a("text", True, sel))
            y += 1
        self.statusline()
        if self.help:
            self.draw_help()
        self.scr.refresh()

    def statusline(self):
        h, w = self.scr.getmaxyx()
        y = h - 1
        mode_kind = {"NORMAL": "peach", "FILTER": "sky", "CONFIRM": "red", "RENAME": "yellow", "ADD": "green"}[self.mode]
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
        if self.focus == "accounts":
            hints = [("Enter", "switch"), ("r", "run here"), ("u", "usage"), ("p", "pause"), ("m", "map folder"),
                     ("a", "add"), ("dd", "remove")]
        else:
            hints = [("dd", "remove rule"), ("Tab", "accounts")]
        hints += [("?", "keys"), ("q", "quit")]
        hx = x + 2
        for k, label in hints:
            if hx + len(k) + len(label) + 4 > w - 2:
                break
            hx = self.put(y, hx, f" {k} ", self.a("key", True))
            hx = self.put(y, hx + 1, label, self.a("dim")) + 2

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
        self.st["default"] = n
        self.save_reload()
        core.signal_bar()
        self.toast(f"✓ {n} is active: every new claude, in any folder, uses it")

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
        def done(name):
            name = name.strip()
            try:
                core.check_name(name)
            except core.VeshaError as e:
                self.toast(str(e), "err")
                return
            self.after = ("add", name)
        self.prompt("ADD", "name for the new account: ", "", done)

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
            self.focus = "folders" if self.focus == "accounts" and self.folders() else "accounts"
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
        if what == "add":
            from .cli import Ctx, cmd_add
            try:
                cmd_add(Ctx([arg]))
            except core.VeshaError as e:
                from . import ui
                ui.err(str(e))
            input("\nPress Enter to go back to the switcher… ")
