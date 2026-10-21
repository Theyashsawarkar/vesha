# 5. A `claude` wrapper decides the account

**Status:** Accepted  
**Date:** 2026-10-21

## Context

Switching has to work "from anywhere, for any project": in every terminal, editor and script that runs `claude`, including ones already open. Exporting `CLAUDE_CONFIG_DIR` from a shell hook only reaches shells started afterwards, and nothing outside a shell.

## Decision

`vesha install-shim` puts a small `claude` script in `~/.local/bin` (before `/usr/bin` on PATH). Each time it runs, it asks vesha which account applies and executes the real Claude Code with that profile. The account is, first match wins: `VESHA_ACCOUNT` (set by `vesha use` for one terminal or `vesha run` for one command), then the closest folder rule above the current folder, then the active account.

## Consequences

- A switch reaches every new `claude` at once, everywhere, with no restart.
- The wrapper costs one Python start (a few tens of milliseconds) per launch; it skips itself when looking for the real `claude`.
- If another `claude` comes earlier on PATH, switching silently does nothing; `vesha doctor` and `vesha switch` check for this and say so.
- The wrapper is marked (`vesha-shim`) so vesha only ever replaces or removes its own file.
