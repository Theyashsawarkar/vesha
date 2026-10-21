# Changelog

Newest first. Releases are tags (`vX.Y.Z`) with `VERSION` in `vesha/__init__.py`.

## v0.3.1 -- 2026-10-21

- **Follows your theme**: with [varna](https://github.com/Theyashsawarkar/varna)
  installed, the switcher and the command-line output take the current
  theme's colours (vesha's own pick under `tools.vesha`, else the
  desktop's); without varna, Catppuccin Mocha as before.

## v0.3.0 -- 2026-10-21

- **Switching reaches running sessions**: the active account's login now
  lives in `~/.claude`, and a switch (`vesha switch`, the switcher, or the
  watcher at the limit) moves the target's login there and the old one to
  its profile. Every `claude` uses the new account from its next message,
  the session that hit the limit included, like claude-swap but without
  copying a login (ADR 9). A switch waits while Claude renews the active
  login, is refused while a session runs inside the target's own profile
  (`--force` overrides), and keeps a renewal that lands mid-swap.
- **Reset times are a day and a time**: "today 9:40 PM", "tomorrow 6:00 AM",
  "Sat 6:00 AM" (a date further out), in the switcher, `vesha usage`,
  `vesha list`, waybar's tooltip and the watcher's notifications, instead
  of "in 4h 12m".

## v0.2.3 -- 2026-10-21

- **Usage bars are thin lines now**: the used part a bold line in green,
  yellow or red, flowing into a faint hairline for the rest, to half a cell.
  No background colour, so they suit a transparent terminal and rows no
  longer run together (v0.2.2's solid pills looked heavy).

## v0.2.2 -- 2026-10-21

- **Better-looking usage bars**, in the switcher and the CLI: rounded pills
  on a soft track, filled to an eighth of a cell, wider in the overview.
- **Their colour follows what's used**: green while there's plenty left,
  yellow from half, red from the warning level (`warn_at`, 85%). Plain
  `[####----]` bars without colour.

## v0.2.1 -- 2026-10-21

- **`vesha import cswap` restores a lost login**: an account vesha has but
  that lost its login (e.g. after `vesha repair`) is signed back in from
  claude-swap's saved copy.
- **`h` / `l`** go to the accounts / folder rules tab (arrows too), and
  `Tab` reaches the folder rules tab even when there are none yet.
- **Rounded capsules** for the tabs, tags, mode and key hints, like the tmux bar.
- Every switcher key is exercised end to end against a throwaway home.

## v0.2.0 -- 2026-10-21

- **Sign in without leaving vesha**: `a` in the switcher asks for a name and
  an email, opens Anthropic's sign-in page in your browser with the email
  filled in, and adds the account when you've entered the emailed code
  there; if the page shows a code, paste it into vesha. `Ctrl+o` reopens
  the page, `Ctrl+y` copies the link, `Esc` cancels and cleans up.
  `vesha add <name> <email>` does the same from a shell; `vesha login`
  fills in the account's email.
- **A new look, like sangam**: a tab strip (accounts, folder rules, the
  account a new claude uses here, auto-switching, `? keys`), the accounts in
  a rounded pane with column headers and a marker on the selected row, and
  an overview pane with usage, login, profile, folders and "what now".
  Stacks into one column on narrow terminals.
- Fixed: the last column of the screen was never drawn; `doctor` no longer
  checks shared files of a profile that isn't made yet.

## v0.1.3 -- 2026-10-21

- **`vesha repair`**: when another tool replaced a profile's login (e.g.
  claude-swap wrote another account into `~/.claude`), two accounts showed
  the same usage under the wrong email. repair makes the records match the
  logins, moves the duplicate profile to vesha's trash folder, forgets the
  numbers cached under the wrong name, and says which account to sign in
  again. It shows the plan and asks first.
- **The switcher flags it**: a red "login changed" tag and a line saying who
  is really signed in; `vesha doctor` points to `vesha repair`.
- **`vesha login <name>`** tells you which account to pick, and refuses one
  that is already another account's.

## v0.1.2 -- 2026-10-21

- **Catches logins changed behind vesha's back**: `vesha doctor` says when a
  profile is now signed in to a different account than the one added (e.g.
  claude-swap or a `/login` changed `~/.claude`), and when two profiles hold
  a copy of the same login.
- **Never renews a copied login**: renewing one copy logs the other out (a
  running session, possibly), so vesha leaves it to Claude Code and says so.

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
