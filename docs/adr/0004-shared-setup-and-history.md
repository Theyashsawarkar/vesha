# 4. One setup and one history for every account

**Status:** Accepted  
**Date:** 2026-10-21

## Context

With a profile per account (ADR 2), each profile would have its own CLAUDE.md, settings, hooks, skills, plugins and agents, and its own conversation history. Keeping several copies in sync by hand defeats the point, and `claude --resume` couldn't continue a conversation that hit one account's limit on another account.

## Decision

`~/.claude` stays the one source. vesha symlinks into every other profile: CLAUDE.md, settings.json, keybindings.json, skills, plugins, agents, commands and output-styles. With `share_history` (on by default) it also links the projects folder, history.jsonl, todos, file-history and plans. Logins and each profile's own `.claude.json` (account identity, per-account caches) are never shared.

## Consequences

- Change a setting or a skill once and every account has it.
- A conversation that ran out on one account continues on another (`claude --continue`).
- A file a profile already has of its own is left alone, never overwritten.
- Turning `share_history` off later leaves existing links until the profile is re-linked.
