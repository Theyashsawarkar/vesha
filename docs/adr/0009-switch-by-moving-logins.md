# 9. Switching moves logins into ~/.claude

**Status:** Accepted  
**Date:** 2026-10-21  
**Supersedes:** [ADR 5](0005-a-wrapper-decides-the-account.md) for the active account (the wrapper still applies folder and terminal rules)

## Context

Until v0.2, switching only changed which profile the next `claude` started with: the wrapper set `CLAUDE_CONFIG_DIR`. Sessions already running kept their account. But the moment you switch is usually the moment a running session hits its limit, and you want *that* session to carry on. claude-swap gets this right by rewriting the login in `~/.claude`: Claude Code re-reads its credentials file, so a running session picks up the new account on its next request. It does it by copying logins, which ADR 3 rules out (rotated tokens log each other's copies out).

## Decision

The active account's login always lives in `~/.claude`. Switching moves logins instead of copying them: the target's profile folder becomes the old account's profile, the old login is written into it, and the target's login replaces `~/.claude/.credentials.json` (each file replaced in one atomic step, `oauthAccount` in each `.claude.json` updated to match). The CLI, the switcher and the watcher all switch this way (`core.activate`).

Guards: a switch waits while Claude is about to renew the active login (renewal rewrites `~/.claude`'s file); it's refused while a session runs inside the target's own profile (that session would lose its login) unless forced; and if Claude renewed the old login anyway in the instant of the swap, the renewed copy is kept for the old account and the new login put back.

## Consequences

- A switch, manual or automatic, reaches every running session from its next message.
- Each login still exists in exactly one place.
- Folder rules, `vesha use` and `vesha run` keep starting other accounts in their profiles.
