# Changelog

Newest first. Releases are tags (`vX.Y.Z`) with `VERSION` in `vesha/__init__.py`.

## v0.1.1 -- 2026-10-21

- **Accounts and profiles moved to `~/.local/state/vesha`**: v0.1.0 kept them
  in `~/.local/share/vesha`, where kosha and `install.sh` put vesha itself.
  They're moved on first run (not while a session runs on an old profile);
  installing or removing vesha never touches a login (ADR 8).
- `vesha service status` shows the watcher's last log lines.
- `vesha list` with no accounts yet is not an error (exit 0); `doctor`
  checks this home's watcher unit, not just systemd.
- The switch note is accurate about folder rules and running sessions.

## v0.1.0 -- 2026-10-21

The first release: every Claude Code account signed in at once, one key to
switch, and automatic switching when the active one hits its limit.

- **Profiles, not swaps**: each account is its own Claude Code profile
  (`CLAUDE_CONFIG_DIR`); the account in `~/.claude` stays where it is.
  Switching never touches a login, and running sessions keep their account.
- **Switch from anywhere**: `vesha switch [name]` changes the account every
  new `claude` uses, in every folder and terminal, through a small `claude`
  wrapper (`vesha install-shim`). `vesha use` for one terminal, `vesha run`
  for one command, optional folder rules with `vesha map`.
- **Automatic switching**: `vesha service install` runs a watcher that
  warns at 85% of either limit (with a "Switch to …" button) and switches
  at 98% to the account with the most room, skipping paused and full ones.
  Each warning is shown once per limit window, even across restarts.
- **The switcher** (`vesha`): every account with its plan, 5-hour and weekly
  usage and reset times, tags for active / here / paused / running sessions,
  and the folder rules. Vim keys: `j`/`k`, `gg`/`G`, `Ctrl+d`/`Ctrl+u`,
  counts, `1-9`, `Tab`, `Enter`, `r`, `u`, `p`, `m`, `a`, `R`/`cw`, `dd`, `y`,
  `/` with `n`/`N`, and `?` for all of them. Adapts from 80 columns up.
- **Shared setup and history**: CLAUDE.md, settings, skills, plugins,
  agents, commands and history are linked from `~/.claude` into every
  profile, so `claude --continue` works across accounts.
- **Usage everywhere**: `vesha usage`, `vesha list` and a waybar module
  (`vesha waybar`) that redraws the moment the account changes.
- **Logins stay safe**: one copy of each login (Claude Code rotates them),
  tokens renewed in place only when Claude isn't running on that profile,
  files private to you, no token ever printed.
- **`vesha import cswap`** brings claude-swap's accounts across.
- `vesha doctor`, `vesha init zsh|bash` (shell hook and completion),
  `--json` output, help for every command, ruff, tests and a website with
  the changelog and design decisions.
