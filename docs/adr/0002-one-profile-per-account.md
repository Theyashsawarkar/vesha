# 2. One Claude Code profile per account

**Status:** Accepted (where profiles live: amended by [ADR 8](0008-data-in-the-state-folder.md))  
**Date:** 2026-10-21

## Context

Claude Code keeps one login in its config folder (`~/.claude`). Tools like claude-swap switch accounts by saving that login away and writing another one in its place. That makes switching global and destructive: every running session's login changes underneath it, a switch while Claude refreshes its token can lose a login, and two accounts can never be used at the same time.

Claude Code also reads `CLAUDE_CONFIG_DIR`: point it at another folder and that folder is a complete, separate profile with its own login.

## Decision

Every account is its own profile. The account already in `~/.claude` stays there (vesha's "main" account, so Claude Code without vesha still works); every other account gets `~/.local/share/vesha/profiles/<name>`. Switching never touches a login: it only changes which profile the next `claude` starts with.

## Consequences

- Any number of accounts are signed in at once; sessions already running keep their account.
- Switching is instant and can't corrupt a login.
- Settings, skills and history would be per profile, so vesha links them (ADR 4).
- Signing in a new account goes through Claude Code's own `/login` in the new profile; vesha never handles a password.
