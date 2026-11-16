# 12. When every account is full, be on the one that frees up first

**Status:** Accepted (refines 6)  
**Date:** 2026-11-16

## Context

ADR 6 left the case where every account is at its limit alone: the watcher
said when the first one resets and stayed on the active account. But the
accounts don't reset together. Staying on one that resets at 1:30 AM while
another frees up at 10:30 PM means the next `claude` message fails for three
hours longer than it has to, or waits for someone to notice and switch by hand.

## Decision

When the active account is at `switch_at`, `auto` is on and no other
account has room, the watcher switches to the unpaused account whose limit
resets first, if that is at least a minute sooner than the active one's:

- An account frees up when **every** window at its limit has reset: a full
  5-hour window that resets soon doesn't help while its week is full.
- Last known numbers count (they are lower bounds until their window
  resets); an account whose reset time is unknown, or whose usage can't be
  read at all, is never picked; one with a known reset beats an active one
  without.
- The minute's margin keeps two accounts resetting together (the API's reset
  times jitter) from swapping back and forth.
- One notification says everything (switched, when it frees up, when the old
  one does); the "reached its limit" one isn't sent again for the new account.
- The watcher then looks again a few seconds after the first reset, instead
  of up to `check_every` later.

Paused accounts stay out, as everywhere else. With `auto` off the watcher
only says which account frees up first.

## Consequences

- With every account full, Claude works again at the earliest moment any of
  them allows, with no one watching the clock.
- A switch to a full account still changes every running session's account;
  that's harmless, since none of them could send anything on the old one.
- An account a session never uses has its numbers asked at most every ten
  minutes, so its reset time can be a little old; usage only grows inside a
  window, so the reset time it gives is still the right one.
