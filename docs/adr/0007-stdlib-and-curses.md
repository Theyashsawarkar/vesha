# 7. Standard library only, curses for the switcher

**Status:** Accepted  
**Date:** 2026-10-21

## Context

vesha's wrapper runs before every `claude`, and its watcher runs all the time; both must start fast and never break because a dependency changed. The switcher needs vim-style navigation and a dense, adaptive layout.

## Decision

Python 3.11's standard library only: `urllib` for the two HTTP calls, `curses` for the switcher, `tomllib` for the config. The switcher's keys follow vim (`j`/`k`, `gg`/`G`, counts, `/`, `dd`, `cw`, `?`), every key is annotated with a `# keybind:` line, and its layout adapts from 80 columns up.

## Consequences

- `git clone` and a symlink are a complete install; nothing to build or pin.
- The UI is drawn by hand; the layout code has to handle narrow terminals itself.
