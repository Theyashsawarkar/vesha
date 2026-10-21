"""vesha's decisions, without the network or real accounts."""
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vesha import core, watch

CONF = dict(core.DEFAULTS)


def st(default="work", **accounts):
    accounts = accounts or {"work": False, "personal": False}
    return {"default": default, "folders": {}, "accounts": {n: {"paused": p} for n, p in accounts.items()}}


def use(**pcts):
    return {n: {"five_hour": {"pct": h, "resets_at": "2099-01-01T00:00:00Z"}, "seven_day": {"pct": w, "resets_at": None}}
            for n, (h, w) in pcts.items()}


class AutoSwitch(unittest.TestCase):
    def setUp(self):
        self.p = mock.patch.object(core, "config", lambda: CONF)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_switches_at_the_limit_to_the_roomiest(self):
        s = st(work=False, personal=False, client=False)
        u = use(work=(99, 40), personal=(30, 90), client=(50, 10))
        self.assertEqual(watch.decide(s, u, CONF, {}), ("switch", "client"))

    def test_weekly_limit_counts(self):
        u = use(work=(10, 99), personal=(20, 20))
        self.assertEqual(watch.decide(st(), u, CONF, {}), ("switch", "personal"))

    def test_never_picks_paused_or_full(self):
        s = st(work=False, personal=True, client=False)
        u = use(work=(100, 10), personal=(0, 0), client=(99, 0))
        self.assertEqual(watch.decide(s, u, CONF, {}), ("full", None))

    def test_auto_off_only_tells(self):
        conf = dict(CONF, auto=False)
        u = use(work=(100, 10), personal=(5, 5))
        self.assertEqual(watch.decide(st(), u, conf, {}), ("full", "personal"))

    def test_warns_once_per_window(self):
        warned = {}
        u = use(work=(88, 10), personal=(5, 5))
        self.assertEqual(watch.decide(st(), u, CONF, warned), ("warn", "personal"))
        self.assertEqual(watch.decide(st(), u, CONF, warned), ("ok", None))

    def test_same_window_despite_jittery_reset_times(self):
        # the API's resets_at differs in its microseconds on every fetch
        warned = {}
        u = use(work=(90, 10), personal=(100, 5))
        u["work"]["five_hour"]["resets_at"] = "2099-01-01T14:20:00.469341+00:00"
        self.assertEqual(watch.decide(st(), u, CONF, warned), ("warn", None))
        u = use(work=(94, 10), personal=(100, 5))
        u["work"]["five_hour"]["resets_at"] = "2099-01-01T14:19:59.912907+00:00"
        self.assertEqual(watch.decide(st(), u, CONF, warned), ("ok", None))
        u["work"]["five_hour"]["pct"] = 99   # reaching the limit is still said, once
        self.assertEqual(watch.decide(st(), u, CONF, warned), ("full", None))
        self.assertEqual(watch.decide(st(), u, CONF, warned), ("ok", None))

    def test_quiet_below_warning(self):
        self.assertEqual(watch.decide(st(), use(work=(40, 40), personal=(5, 5)), CONF, {}), ("ok", None))

    def test_stale_numbers_never_switch(self):
        u = use(work=(100, 10), personal=(5, 5))
        u["work"]["stale"] = "offline"
        self.assertEqual(watch.decide(st(), u, CONF, {}), ("ok", None))


class Resolve(unittest.TestCase):
    def test_terminal_then_folder_then_default(self):
        d = tempfile.mkdtemp()
        sub = os.path.join(d, "a", "b")
        os.makedirs(sub)
        s = {"default": "work", "accounts": {"work": {}, "personal": {}}, "folders": {d: "personal"}}
        self.assertEqual(core.resolve(s, sub, {})[0], "personal")
        self.assertEqual(core.resolve(s, "/", {})[0], "work")
        self.assertEqual(core.resolve(s, sub, {"VESHA_ACCOUNT": "work"}), ("work", "this terminal"))

    def test_nearest_folder_wins(self):
        d = tempfile.mkdtemp()
        inner = os.path.join(d, "inner")
        os.makedirs(inner)
        s = {"default": "x", "accounts": {"x": {}, "outer": {}, "in": {}}, "folders": {d: "outer", inner: "in"}}
        self.assertEqual(core.resolve(s, inner, {})[0], "in")


class Misc(unittest.TestCase):
    def test_names(self):
        for bad in ("Work", "", "a b", "-x", "x" * 40):
            with self.assertRaises(core.VeshaError):
                core.check_name(bad)
        self.assertEqual(core.check_name("client-x"), "client-x")

    def test_resets_in(self):
        iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 3 * 3600 + 120))
        self.assertTrue(core.resets_in(iso)[0].startswith("3h"))


if __name__ == "__main__":
    unittest.main()
