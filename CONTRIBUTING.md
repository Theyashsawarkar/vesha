# Contributing to vesha

Thanks for helping. Bug reports, ideas and pull requests are all welcome.

## Development setup

```sh
git clone https://github.com/Theyashsawarkar/vesha ~/code/vesha
cd ~/code/vesha
ruff check .
python -m unittest discover -s tests -v
HOME=$(mktemp -d) bin/vesha list      # try it without touching your real accounts
```

To use your checkout as your real vesha: `kosha link vesha ~/code/vesha`
(and `kosha unlink vesha` afterwards), or point `~/.local/bin/vesha` at it.

## How it fits together

- `bin/vesha`: the entry point.
- `vesha/cli.py`: every command, its help and its output.
- `vesha/core.py`: accounts and profiles, which account applies where,
  usage and token renewal, the wrapper, claude-swap import.
- `vesha/watch.py`: the background watcher (warnings, automatic switching).
- `vesha/tui.py`: the switcher.
- `vesha/ui.py`: colours, tables, progress and prompts.

## Rules

- **Never copy a login** (ADR 3): read and renew credentials in place, and
  never while Claude Code runs on that profile.
- **Never print a token**, and keep real emails out of tests, screenshots,
  issues and logs.
- **Switching never touches a login** (ADR 2): it only changes which profile
  the next `claude` uses.
- **Standard library only** (ADR 7).
- **Keys**: every switcher key has a `# keybind: Vesha/switcher | <keys> |
  <Verb> <object>` line in `vesha/tui.py`, an entry in the `?` sheet and a
  row in the README (CI checks the README).
- Every change gets a `CHANGELOG.md` entry; releases are tags `vX.Y.Z` with
  `VERSION` in `vesha/__init__.py` bumped. The website is generated:
  `python3 scripts/build-site.py` after changing the README, CHANGELOG or
  ADRs. A significant design decision gets a new ADR in `docs/adr/`.

## Pull requests

Describe what and why, and tick the template's checklist. By contributing
you agree your work is released under the [MIT License](LICENSE).
