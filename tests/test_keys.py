"""The switcher's keys: the table is consistent and the annotations match it."""
import curses
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from vesha import keys, tui  # noqa: E402

VERBS = {"add", "cancel", "confirm", "copy", "enter", "jump", "map", "move", "open", "quit", "refresh",
         "remove", "rename", "run", "scroll", "search", "send", "set", "show", "switch", "toggle", "clear"}


class Keys(unittest.TestCase):
    def test_annotations_are_generated(self):
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "keybinds.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_descriptions_start_with_a_verb(self):
        for b in tui.BINDS + [b for bs in tui.TYPING.values() for b in bs]:
            if b.desc:
                self.assertIn(b.desc.split()[0].lower(), VERBS, b.desc)

    def test_reserved_groups_keep_their_meaning(self):
        # Every leader key lives in a reserved group, and means what the group says.
        meaning = {" t": "tab:", " y": "copy:", " f": "search", " d": "remove", " a": "add", " e": "rename",
                   " o": ("run", "open:"), " g": "goto:", " m": ("pause", "map"), " q": "quit", " ?": "help",
                   "  ": "palette", " r": "refresh"}
        for b in tui.BINDS:
            if b.seq.startswith(" ") and len(b.seq) > 1:
                self.assertIn(b.seq[:2], keys.GROUPS, b.seq)
                want = meaning[b.seq[:2]]
                self.assertTrue(b.action.startswith(want if isinstance(want, tuple) else (want,)), (b.seq, b.action))

    def test_no_key_hides_another_in_the_same_view(self):
        for view in ("accounts", "folders", "signin"):
            table = {b.seq: b for b in tui.BINDS if b.applies("normal", view)}
            for seq in table:
                longer = [s for s in table if s != seq and s.startswith(seq)]
                self.assertFalse(longer, f"{view}: {seq!r} would never run, {longer} start with it")

    def test_sequences(self):
        km = keys.Keymap([b for b in tui.BINDS if b.applies("normal", "accounts")])
        m = keys.Machine()
        self.assertEqual(m.feed(km, "3").kind, "pending")
        r = m.feed(km, "j")
        self.assertEqual((r.kind, r.bind.action, r.count), ("run", "move:1", 3))
        for tok in (" ", "m"):
            self.assertEqual(m.feed(km, tok).kind, "pending")
        self.assertEqual(m.feed(km, "f").bind.action, "map")
        self.assertEqual(m.feed(km, "d").kind, "pending")
        self.assertEqual(m.feed(km, "<Esc>").kind, "cancel")

    def test_curses_tokens(self):
        self.assertEqual(tui.curses_token(10), "<CR>")
        self.assertEqual(tui.curses_token(4), "<C-d>")
        self.assertEqual(tui.curses_token(ord(" ")), " ")
        self.assertEqual(tui.curses_token(curses.KEY_DOWN), "<Down>")
        # get_wch gives str for typed characters and int for key codes
        self.assertEqual(tui.curses_token("\n"), "<CR>")
        self.assertEqual(tui.curses_token("j"), "j")
        self.assertIsNone(tui.curses_token(curses.KEY_F1))      # F1 types nothing into a prompt
        self.assertIsNone(tui.curses_token(curses.KEY_IC))
        self.assertEqual(tui.curses_token(chr(curses.KEY_UP)), chr(curses.KEY_UP))   # "ă" is a letter, not Up

    def test_vendored_keys_header(self):
        first = (ROOT / "vesha" / "keys.py").read_text().splitlines()[0]
        self.assertTrue(re.match(r"# Vendored from Vyom's vyom/keys.py v\d", first), first)


if __name__ == "__main__":
    unittest.main()
