## What and why

<!-- What this changes and why. -->

## Checklist

- [ ] `ruff check .` and `python -m unittest discover -s tests` pass
- [ ] Tried with a throwaway home (`HOME=$(mktemp -d) bin/vesha ...`), not only my real accounts
- [ ] New or changed keys: the `# keybind:` lines, the `?` sheet and the README agree
- [ ] A `CHANGELOG.md` entry; the website rebuilt (`python3 scripts/build-site.py`) if README, CHANGELOG or ADRs changed
- [ ] No token, credential or real email in code, tests, screenshots or logs
