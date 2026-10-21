# 6. A watcher switches at the limit

**Status:** Accepted  
**Date:** 2026-10-21

## Context

The point of several accounts is to keep working when one runs out. Checking usage by hand and switching just before the limit is exactly the interruption vesha should remove; but switching too eagerly, or to an account that's nearly out itself, is worse than not switching.

## Decision

A systemd user service runs `vesha watch`, which checks the active account's 5-hour and weekly usage (Claude Code's own usage endpoint) every two minutes, every minute once it's close:

- at `warn_at` (85%) of either window it notifies once per window, offering to switch;
- at `switch_at` (98%), with `auto` on, it makes the best alternative active and notifies;
- the best alternative is the account with the lowest worse window (max of 5-hour and weekly), never a paused one, one at its limit, or one whose numbers are stale.

A window is identified by its reset time rounded to ten minutes, and what was already said is kept on disk, so neither the API's jitter nor a restart repeats a notification. The watcher never stops a running session: sessions keep their account, new ones use the new one.

## Consequences

- Hitting a limit costs one restart of the session (`claude --continue`, the history is shared).
- With every account at its limit vesha says when the first one resets, and does nothing else.
- Usage is read every couple of minutes per active account only, well inside what Claude Code itself does.
