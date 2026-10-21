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


class Migrate(unittest.TestCase):
    def paths(self, root):
        new = os.path.join(root, "state", "vesha")
        return mock.patch.multiple(core, LEGACY=os.path.join(root, "share", "vesha"), DATA=new,
                                   STATE=os.path.join(new, "accounts.json"), PROFILES=os.path.join(new, "profiles"))

    def legacy(self, root):
        old = os.path.join(root, "share", "vesha")
        os.makedirs(os.path.join(old, "profiles", "work"))
        with open(os.path.join(old, "accounts.json"), "w") as f:
            f.write('{"accounts": {"work": {}}, "default": "work", "folders": {}}')
        return old

    def test_moves_accounts_and_profiles_out_of_the_install_folder(self):
        root = tempfile.mkdtemp()
        old = self.legacy(root)
        with self.paths(root), mock.patch.object(core, "running_profiles", lambda: {}):
            self.assertEqual(core.load()["default"], "work")
            self.assertTrue(os.path.isdir(os.path.join(core.PROFILES, "work")))
        self.assertFalse(os.path.exists(old))

    def test_never_from_a_checkout_or_under_a_running_session(self):
        root = tempfile.mkdtemp()
        old = self.legacy(root)
        busy = {os.path.join(old, "profiles", "work"): 1}
        with self.paths(root), mock.patch.object(core, "running_profiles", lambda: busy):
            self.assertEqual(core.load()["accounts"], {})
        os.makedirs(os.path.join(old, ".git"))
        with self.paths(root), mock.patch.object(core, "running_profiles", lambda: {}):
            self.assertEqual(core.load()["accounts"], {})
        self.assertTrue(os.path.exists(os.path.join(old, "accounts.json")))


class Repair(unittest.TestCase):
    def test_main_overwritten_with_another_accounts_login(self):
        root = tempfile.mkdtemp()
        main, prof = os.path.join(root, ".claude"), os.path.join(root, "state", "profiles")
        who = {main: ("w@acme.dev", "Acme"), os.path.join(prof, "work"): ("w@acme.dev", "Acme")}
        os.makedirs(os.path.join(prof, "work"))
        s = {"default": "personal", "folders": {}, "accounts": {
            "personal": {"main": True, "email": "p@example.com", "org": "P"},
            "work": {"main": False, "email": "w@acme.dev", "org": "Acme"}}}

        def ident(d):
            e, o = who.get(d, ("", ""))
            return {"email": e, "org": o, "plan": "Team", "signed_in": bool(e)}
        with mock.patch.multiple(core, MAIN_DIR=main, PROFILES=prof, DATA=os.path.join(root, "state"),
                                 CACHE=os.path.join(root, "cache"), identity=ident):
            plan = core.repair_plan(s)
            self.assertEqual(len(plan), 1)
            plan[0][1](s)
        self.assertTrue(s["accounts"]["work"]["main"])
        self.assertFalse(s["accounts"]["personal"]["main"])
        self.assertEqual(s["default"], "work")
        self.assertFalse(os.path.exists(os.path.join(prof, "work")))   # moved to trash, not deleted
        self.assertEqual(len(os.listdir(os.path.join(root, "state", "trash"))), 1)


class Activate(unittest.TestCase):
    """Switching moves logins: the target's into ~/.claude, the old one out."""

    def setUp(self):
        import json
        self.json = json
        self.root = tempfile.mkdtemp()
        self.main = os.path.join(self.root, ".claude")
        self.main_json = os.path.join(self.root, ".claude.json")
        self.prof = os.path.join(self.root, "state", "profiles")
        os.makedirs(self.main)
        os.makedirs(os.path.join(self.prof, "b"))
        self.write(os.path.join(self.main, ".credentials.json"), {"claudeAiOauth": {"refreshToken": "rt-a", "expiresAt": 0}})
        self.write(self.main_json, {"oauthAccount": {"emailAddress": "a@x"}, "projects": {"keep": 1}})
        self.write(os.path.join(self.prof, "b", ".credentials.json"), {"claudeAiOauth": {"refreshToken": "rt-b"}})
        self.write(os.path.join(self.prof, "b", ".claude.json"), {"oauthAccount": {"emailAddress": "b@x"}})
        self.st = {"default": "a", "folders": {}, "accounts": {"a": {"main": True}, "b": {"main": False}}}
        self.patch = mock.patch.multiple(core, MAIN_DIR=self.main, MAIN_JSON=self.main_json, PROFILES=self.prof,
                                         DATA=os.path.join(self.root, "state"), STATE=os.path.join(self.root, "state", "a.json"),
                                         running_profiles=lambda: {})
        self.patch.start()

    def tearDown(self):
        self.patch.stop()

    def write(self, path, data):
        with open(path, "w") as f:
            self.json.dump(data, f)

    def read(self, path):
        with open(path) as f:
            return self.json.load(f)

    def test_moves_logins_never_copies(self):
        with mock.patch.object(core.time, "sleep", lambda s: None):
            old = core.activate(self.st, "b")
        self.assertEqual(old, "a")
        self.assertEqual(self.read(os.path.join(self.main, ".credentials.json"))["claudeAiOauth"]["refreshToken"], "rt-b")
        self.assertEqual(self.read(os.path.join(self.prof, "a", ".credentials.json"))["claudeAiOauth"]["refreshToken"], "rt-a")
        self.assertFalse(os.path.exists(os.path.join(self.prof, "b")))           # b's login lives only in ~/.claude now
        self.assertEqual(self.read(self.main_json)["oauthAccount"]["emailAddress"], "b@x")
        self.assertEqual(self.read(self.main_json)["projects"], {"keep": 1})     # the rest of ~/.claude.json stays
        self.assertEqual(self.read(os.path.join(self.prof, "a", ".claude.json"))["oauthAccount"]["emailAddress"], "a@x")
        self.assertTrue(self.st["accounts"]["b"]["main"] and not self.st["accounts"]["a"]["main"])
        self.assertEqual(self.st["default"], "b")

    def test_refuses_while_the_target_profile_is_in_use(self):
        busy = {os.path.realpath(os.path.join(self.prof, "b")): 1}
        with mock.patch.object(core, "running_profiles", lambda: busy):
            with self.assertRaises(core.VeshaError):
                core.activate(self.st, "b")
        self.assertTrue(os.path.exists(os.path.join(self.prof, "b", ".credentials.json")))   # nothing moved

    def test_a_renewal_during_the_swap_is_kept(self):
        def renew(_s):   # Claude renews the old login into ~/.claude right after the swap
            self.write(os.path.join(self.main, ".credentials.json"), {"claudeAiOauth": {"refreshToken": "rt-a2"}})
        with mock.patch.object(core.time, "sleep", renew):
            core.activate(self.st, "b")
        self.assertEqual(self.read(os.path.join(self.main, ".credentials.json"))["claudeAiOauth"]["refreshToken"], "rt-b")
        self.assertEqual(self.read(os.path.join(self.prof, "a", ".credentials.json"))["claudeAiOauth"]["refreshToken"], "rt-a2")


class ResetLabels(unittest.TestCase):
    def iso(self, days, hour=9):
        from datetime import datetime, timedelta
        d = (datetime.now().astimezone() + timedelta(days=days)).replace(hour=hour, minute=40, second=0, microsecond=0)
        return d.isoformat()

    def test_today_tomorrow_weekday_date(self):
        from datetime import datetime, timedelta
        self.assertEqual(core.resets_in(self.iso(0, 23))[1], "today 11:40 PM")
        self.assertEqual(core.resets_in(self.iso(1))[1], "tomorrow 9:40 AM")
        wd = (datetime.now() + timedelta(days=3)).strftime("%a")
        self.assertEqual(core.resets_in(self.iso(3))[1], f"{wd} 9:40 AM")
        self.assertRegex(core.resets_in(self.iso(10))[1], r"^[A-Z][a-z]{2} \d{1,2} 9:40 AM$")


if __name__ == "__main__":
    unittest.main()
