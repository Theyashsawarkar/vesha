# vesha -- notes for agents

A Claude Code multi-account manager: the active account's login lives in
~/.claude and switching moves logins in and out (core.activate, ADR 9), so
running sessions follow; other accounts are profiles (`CLAUDE_CONFIG_DIR`)
used by folder rules, `vesha use` and `vesha run` through a `claude`
wrapper; a watcher switches at the usage limit. Its own repo, pulled into Vayu
(github.com/Theyashsawarkar/vayu, whose CLAUDE.md "Plugins" rules apply);
it must work without Vayu.

- `bin/vesha` entry; `vesha/cli.py` commands; `vesha/core.py` accounts,
  resolution, usage, tokens, wrapper; `vesha/watch.py` watcher;
  `vesha/tui.py` switcher; `vesha/ui.py` output helpers.
- **Never print, log or copy a token**, and never refresh one while Claude
  runs on that profile (ADR 3). Keep real emails out of output you show,
  tests and screenshots (use example.com).
- Test with a throwaway HOME (`HOME=$(mktemp -d) bin/vesha ...`), never by
  switching the user's real accounts unless asked: a real switch changes the
  account of every running Claude session, yours included.
- Keys in the switcher: `# keybind: Vesha/switcher | <keys> | <Verb> <object>`
  lines in tui.py, the `?` sheet and the README must agree; in Vayu run
  `~/.local/bin/keybind-search.py --check`.
- Standard library only. `ruff check .` and `python -m unittest discover -s tests` must pass.
- Every change: a CHANGELOG.md entry; releases are tags with `VERSION` bumped.
- The website (docs/, GitHub Pages) is generated: after changing README.md, CHANGELOG.md or docs/adr/, run `python3 scripts/build-site.py` and commit docs/ (CI checks it). A significant design decision gets a new ADR in docs/adr/ (next number; supersede, never rewrite).
