# 10. The switcher speaks the Space grammar

**Status:** Accepted  
**Date:** 2026-11-08

## Context

The switcher had vim-flavoured keys of its own: `r` ran claude (in every other Vayu tool `r` refreshes), `u` refreshed (vim's undo), `h`/`l` switched tabs, and a number alone jumped to an account after a 0.6 s wait, which also made a count before any other key jump first. Every Vayu tool picked its letters separately, so the same key meant different things one popup apart.

## Decision

The switcher follows the grammar every Vayu tool shares (Vyom ADR 0008): normal mode by default and insert mode only in prompts and the sign-in code field; `Space` is the leader, its groups mean the same thing everywhere (`t` tabs, `y` copy, `a` add, `d` delete, `e` edit, `o` open, `g` go to, `m` mark, `f` find, `r` refresh, `Space` the palette); `H`/`L` switch tabs; digits are counts; anything that removes asks and only `y` says yes.

The keys are data (`BINDS` in `vesha/tui.py`), resolved by Vyom's keys module, vendored as `vesha/keys.py` (standard library only, so vesha stays dependency-free). Help, palette, which-key strip and the `# keybind:` lines all come from that table; `scripts/keybinds.py --check` keeps the annotations in step.

## Consequences

- Keys moved (`o` runs, `r` refreshes, `H`/`L` tabs, `yy` copies, `Space a a` adds); old letters that don't clash still work, and `u` says where refreshing went for one release.
- No more waiting after a digit.
- A change to the shared grammar reaches vesha by vendoring keys.py again (`vendor-keys.sh --check` finds a stale copy).
