# 11. Live usage from the status line

**Status:** Accepted (refines 6)  
**Date:** 2026-11-09

## Context

The watcher (ADR 6) read usage only from Claude Code's usage endpoint and
ignored numbers it couldn't refresh. That endpoint rate-limits hard: with the
watcher asking for every account each minute near a limit, and the bar asking
too, it answered 429 for long stretches. The active account then had only
stale numbers, so it stayed active at 100% and nothing switched.

Claude Code already gets each account's 5-hour and weekly utilization with
every reply, and passes it to the status line command as `rate_limits`.

## Decision

- Claude Code's status line runs `vesha feed`, installed by `vesha service
  install` in ~/.claude/settings.json (shared into every profile). It records
  the limits as that account's usage, wakes the watcher (SIGUSR1) near a
  limit, then runs the status line that was there before, which vesha keeps
  in its state folder, never in the command line.
- The session's profile (`CLAUDE_CONFIG_DIR`, else ~/.claude and the active
  account) says whose numbers they are. Right after a switch, a ~/.claude
  session still shows the old login's numbers until its next reply: those are
  ignored when they haven't changed since the switch, or when their weekly
  reset time is another account's and not this one's.
- Numbers are lower bounds until their window resets, since usage only grows
  inside one: stale numbers still switch, and a window past its reset counts
  as empty.
- The endpoint is asked only for numbers older than a TTL (a minute when
  close), other accounts' only near a limit, and never during a 429 backoff
  (1, 2, 4 ... 15 minutes). The cache is locked and merged by age.
- `switch_at` defaults to 95%.

## Consequences

- Switching follows each message instead of a two-minute poll, and works
  while the endpoint is rate-limiting.
- vesha owns the status line command; a status line of your own still shows,
  run by `vesha feed`. Each update costs a short Python start (~90 ms).
- An account no session is using is still checked through the endpoint.
