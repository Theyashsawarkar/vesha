"""kosha's terminal interface: colours (Catppuccin Mocha), boxed tables,
a live multi-line progress display, and the transaction summary. Falls
back to plain text when stdout isn't a terminal or NO_COLOR is set."""
import os
import shutil
import sys
import threading
import time
import unicodedata

TTY = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None and os.environ.get("TERM") != "dumb"
_COLORS = {
    "text": (205, 214, 244), "sub": (166, 173, 200), "dim": (127, 132, 156), "faint": (88, 91, 112),
    "mauve": (203, 166, 247), "pink": (245, 194, 231), "green": (166, 227, 161), "yellow": (249, 226, 175),
    "peach": (250, 179, 135), "red": (243, 139, 168), "sky": (137, 220, 235), "blue": (137, 180, 250),
    "teal": (148, 226, 213), "lavender": (180, 190, 254),
}


def set_color(on):
    global TTY
    TTY = on


def c(text, color=None, bold=False, dim=False):
    if not TTY:
        return str(text)
    codes = []
    if bold:
        codes.append("1")
    if dim:
        codes.append("2")
    if color:
        r, g, b = _COLORS[color]
        codes.append(f"38;2;{r};{g};{b}")
    return f"\033[{';'.join(codes)}m{text}\033[0m" if codes else str(text)


def width(text):
    """Display width without ANSI codes (wide characters count 2)."""
    out, i, s = 0, 0, str(text)
    while i < len(s):
        if s[i] == "\033":
            j = s.find("m", i)
            i = j + 1 if j != -1 else len(s)
            continue
        out += 2 if unicodedata.east_asian_width(s[i]) in "WF" else (0 if unicodedata.combining(s[i]) else 1)
        i += 1
    return out


def pad(text, w, right=False):
    gap = max(0, w - width(text))
    return (" " * gap + str(text)) if right else (str(text) + " " * gap)


def cols():
    return shutil.get_terminal_size((100, 24)).columns


def out(text=""):
    sys.stdout.write(str(text) + "\n")
    sys.stdout.flush()


# ===================================================================== pieces
ICON = {"ok": "✓", "err": "✗", "warn": "!", "info": "•", "arrow": "→", "step": "❯"}


def ok(msg):
    out(f"{c(ICON['ok'], 'green', bold=True)} {msg}")


def warn(msg):
    out(f"{c(ICON['warn'], 'yellow', bold=True)} {msg}")


def err(msg):
    sys.stderr.write(f"{c(ICON['err'], 'red', bold=True)} {msg}\n")


def note(msg):
    out(f"{c(ICON['info'], 'dim')} {c(msg, 'dim')}")


def header(title, right=""):
    """A full-width rule with the title, like nala's section headers."""
    w = min(cols(), 110)
    left = f" {title} "
    rgt = f" {right} " if right else ""
    line = "━" * max(4, w - width(left) - width(rgt) - 2)
    out(c("━━", "mauve") + c(left, "text", bold=True) + c(line, "faint") + (c(rgt, "dim") if rgt else ""))


def table(rows, headers, aligns=None, title=None):
    """A rounded, boxed table. rows: lists of (already coloured) strings."""
    aligns = aligns or ["l"] * len(headers)
    w = [max([width(h) for h in [headers[i]]] + [width(r[i]) for r in rows]) for i in range(len(headers))]
    avail = min(cols(), 140) - (3 * len(w) + 1)
    while sum(w) > avail and max(w) > 12:   # squeeze the widest column to fit the terminal
        i = w.index(max(w))
        w[i] -= 1
    def cell(text, i):
        t = str(text)
        if width(t) > w[i]:
            plain = _strip(t)
            t = plain[: max(1, w[i] - 1)] + "…"
        return pad(t, w[i], aligns[i] == "r")
    bc = lambda s: c(s, "faint")
    top = bc("╭─" + "─┬─".join("─" * x for x in w) + "─╮")
    mid = bc("├─" + "─┼─".join("─" * x for x in w) + "─┤")
    bot = bc("╰─" + "─┴─".join("─" * x for x in w) + "─╯")
    if title:
        header(title)
    out(top)
    out(bc("│ ") + bc(" │ ").join(c(cell(h, i), "sub", bold=True) for i, h in enumerate(headers)) + bc(" │"))
    out(mid)
    for r in rows:
        out(bc("│ ") + bc(" │ ").join(cell(x, i) for i, x in enumerate(r)) + bc(" │"))
    out(bot)


def _strip(s):
    import re
    return re.sub(r"\033\[[0-9;]*m", "", s)


def summary(parts):
    """`Summary: Install 2 · Upgrade 3 · Remove 1` with coloured counts."""
    bits = [f"{label} {c(n, color, bold=True)}" for label, n, color in parts if n]
    out(c("Summary", "text", bold=True) + c(":  ", "dim") + c("  ·  ", "faint").join(bits))


def confirm(question="Do you want to continue?", default=True, assume=None):
    """[Y/n]: one keypress on a terminal (y, n, Enter for the default, Esc or
    Ctrl-C for no), echoed as the answer; the default without one."""
    if assume is not None:
        return assume
    if not sys.stdin.isatty():
        return default
    hint = "[Y/n]" if default else "[y/N]"
    sys.stdout.write(f"{c('?', 'mauve', bold=True)} {c(question, 'text', bold=True)} {c(hint, 'dim')} ")
    sys.stdout.flush()
    ans = None
    try:
        import termios
        import tty
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            while ans is None:
                ch = sys.stdin.read(1)
                if ch in ("\n", "\r"):
                    ans = default
                elif ch.lower() == "y":
                    ans = True
                elif ch.lower() == "n" or ch in ("\x1b", "\x03", "\x04", ""):
                    ans = False
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except (ImportError, OSError):   # no terminal control (termios.error is an OSError)
        try:
            line = input().strip().lower()
        except EOFError:
            line = ""
        ans = default if not line else line in ("y", "yes")
        return ans
    out(c("Yes", "green", bold=True) if ans else c("No", "red", bold=True))
    return ans


def elapsed(t0):
    s = time.monotonic() - t0
    return f"{s:.1f}s" if s < 60 else f"{int(s // 60)}m {int(s % 60)}s"


# ===================================================================== live progress
VERBOSE = False
_print_lock = threading.Lock()


def set_verbose(on):
    global VERBOSE
    VERBOSE = on


def trace(msg):
    """A verbose-only detail line (git commands and their timing)."""
    if VERBOSE:
        with _print_lock:
            sys.stderr.write(f"   {c('│', 'faint')} {c(msg, 'dim')}\n")
            sys.stderr.flush()


class Progress:
    """A live board, one row per package, redrawn in place while work runs
    in parallel, with a footer of counts and the time so far:

        ⠹ ganit    fetching tags…        ━━━━━━━━━━──────
        ✓ dvara    v0.1.4 → v0.1.5                   0.8s
        ─ ✓ 1  ⠹ 1 running  · 4 waiting                1.2s

    In verbose mode, or without a terminal, every change is a plain line
    instead (with the time), so output can be logged or read by scripts."""
    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    STYLE = {"ok": ("✓", "green"), "warn": ("!", "yellow"), "err": ("✗", "red"), "skip": ("–", "dim"),
             "cancel": ("✗", "dim")}

    def __init__(self, names, title=None, verb="working", noun="account"):
        self.names = list(dict.fromkeys(names))
        self.rows = {n: ["wait", "waiting", None, None] for n in self.names}   # kind, text, start, end
        self.lock = threading.Lock()
        self.frame = 0
        self.title = title
        self.verb = verb
        self.drawn = 0
        self.stop_ev = threading.Event()
        self.nw = max([width(n) for n in self.names] + [4])
        self.t0 = time.monotonic()
        self.noun = noun
        self.live = TTY and not VERBOSE

    def __enter__(self):
        if self.title:
            header(self.title, f"{len(self.names)} {self.noun}{'s' if len(self.names) != 1 else ''}")
        if self.live:
            sys.stdout.write("\033[?25l")
            self._draw()   # the rows appear at once, not after the first tick
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()
        return self

    def __exit__(self, exc_type, *exc):
        if exc_type is not None:   # interrupted or failed: say what didn't finish
            with self.lock:
                for r in self.rows.values():
                    if r[0] in ("run", "wait"):
                        r[0], r[1], r[3] = "cancel", "cancelled", time.monotonic()
        self.stop_ev.set()
        if self.live:
            self.thread.join()
            self._draw(final=True)
            sys.stdout.write("\033[?25h")
            sys.stdout.flush()
        return False

    # ---- state
    def set(self, name, kind, text):
        """kind: wait | run | ok | warn | err | skip"""
        now = time.monotonic()
        with self.lock:
            r = self.rows.setdefault(name, ["wait", "", None, None])
            if kind == "run" and r[2] is None:
                r[2] = now
            if kind in self.STYLE:
                r[3] = now
                r[2] = r[2] or now
            r[0], r[1] = kind, text
        if not self.live and (VERBOSE or kind in self.STYLE):
            self._plain(name, kind, text, now)

    def counts(self):
        out = {}
        for r in self.rows.values():
            out[r[0]] = out.get(r[0], 0) + 1
        return out

    # ---- plain output (verbose / no terminal)
    def _plain(self, name, kind, text, now):
        t = c(f"{now - self.t0:6.2f}s", "faint")
        icon, color = self.STYLE.get(kind, ("›", "mauve"))
        with _print_lock:
            sys.stdout.write(f"{t} {c(icon, color, bold=True)} {pad(c(name, 'text', bold=True), self.nw)}  {text}\n")
            sys.stdout.flush()

    # ---- live board
    def _loop(self):
        while not self.stop_ev.wait(0.08):
            self.frame += 1
            self._draw()

    def _row(self, name, now):
        kind, text, start, end = self.rows[name]
        nm = pad(name, self.nw)
        if kind == "run":
            bar_w = 16
            pos = self.frame % (bar_w * 2)
            pos = pos if pos < bar_w else bar_w * 2 - pos
            bar = c("━" * pos, "faint") + c("━━━━", "mauve") + c("━" * max(0, bar_w - pos), "faint")
            spent = c(f"{now - start:4.1f}s", "faint") if start else ""
            return (f"{c(self.FRAMES[self.frame % 10], 'mauve', bold=True)} {c(nm, 'text', bold=True)}  "
                    f"{pad(c(text, 'sub'), 30)} {bar} {spent}")
        if kind in self.STYLE:
            icon, color = self.STYLE[kind]
            dur = c(f"{end - start:4.1f}s", "faint") if start and end else ""
            body = c(text, "red") if kind == "err" else (c(text, "dim") if kind in ("skip", "cancel") else text)
            line = f"{c(icon, color, bold=True)} {c(nm, 'text', bold=kind != 'skip') if kind != 'skip' else c(nm, 'dim')}  {body}"
            room = min(cols(), 110) - width(line) - 6
            return line + " " * max(1, room) + dur if dur and room > 0 else line
        return f"{c('·', 'faint')} {c(nm, 'dim')}  {c(text, 'faint')}"

    def _footer(self, now):
        n = self.counts()
        bits = []
        for kind, label, color in (("ok", "", "green"), ("warn", "", "yellow"), ("err", "", "red"), ("skip", "skipped", "dim")):
            if n.get(kind):
                icon = self.STYLE[kind][0]
                bits.append(c(f"{icon} {n[kind]}" + (f" {label}" if label else ""), color))
        if n.get("run"):
            bits.append(c(f"{self.FRAMES[self.frame % 10]} {n['run']} {self.verb}", "mauve"))
        if n.get("wait"):
            bits.append(c(f"· {n['wait']} waiting", "faint"))
        if n.get("cancel"):
            bits.append(c(f"✗ {n['cancel']} cancelled", "dim"))
        left = c("╰─ ", "faint") + c("  ", "faint").join(bits)
        t = c(elapsed(self.t0), "dim")
        room = min(cols(), 110) - width(left) - width(t) - 1
        return left + " " * max(2, room) + t

    def _draw(self, final=False):
        now = time.monotonic()
        with self.lock:
            names = self.names
            limit = max(4, shutil.get_terminal_size((100, 24)).lines - 4)
            if len(names) > limit and not final:
                # too many rows for the screen: running first, then waiting, then the latest finished
                run = [n for n in names if self.rows[n][0] == "run"]
                wait = [n for n in names if self.rows[n][0] == "wait"]
                fin = sorted((n for n in names if self.rows[n][0] not in ("run", "wait")),
                             key=lambda n: self.rows[n][3] or 0, reverse=True)
                names = (run + wait + fin)[:limit]
                names.sort(key=self.names.index)
            lines = [self._row(n, now) for n in names] + [self._footer(now)]
        buf = [f"\033[{self.drawn}F"] if self.drawn else []
        buf += ["\033[2K" + line + "\n" for line in lines]
        if self.drawn > len(lines):   # fewer rows than last time: clear the leftovers
            buf += ["\033[2K\n"] * (self.drawn - len(lines)) + [f"\033[{self.drawn - len(lines)}F"]
        with _print_lock:
            sys.stdout.write("".join(buf))
            sys.stdout.flush()
        self.drawn = len(lines)


class Spinner:
    """A single spinner line for a short wait ("checking for updates")."""

    def __init__(self, text):
        self.text = text
        self.ev = threading.Event()

    def __enter__(self):
        if TTY:
            sys.stdout.write("\033[?25l")
            self.t = threading.Thread(target=self._spin, daemon=True)
            self.t.start()
        return self

    def _spin(self):
        i = 0
        while not self.ev.wait(0.08):
            sys.stdout.write(f"\r\033[2K{c(Progress.FRAMES[i % 10], 'mauve')} {c(self.text, 'sub')}")
            sys.stdout.flush()
            i += 1

    def __exit__(self, *exc):
        self.ev.set()
        if TTY:
            self.t.join()
            sys.stdout.write("\r\033[2K\033[?25h")
            sys.stdout.flush()
