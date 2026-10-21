# 3. Never copy a login

**Status:** Accepted  
**Date:** 2026-10-21

## Context

Claude Code's OAuth refresh tokens rotate: each refresh returns a new refresh token and invalidates the old one. If the same login existed in two places (a backup, a snapshot, a second profile), whichever copy refreshed second would hold a dead token and be logged out.

vesha needs a token to read each account's usage, and sometimes a fresh one.

## Decision

Each login exists in exactly one file, its profile's `.credentials.json`. vesha reads it in place; when the access token has expired it refreshes it and writes the new tokens back to that same file, atomically and with mode 0600, and only when no Claude Code process is running on that profile (found through `/proc/<pid>/environ`), since Claude would refresh it too and the two would race. While Claude runs, the last known usage is shown instead.

Importing from claude-swap moves each saved login into its profile once; vesha keeps no copies.

## Consequences

- Accounts don't log each other out.
- Usage for an account in use may be a few minutes old; it's marked as such.
- No token is ever printed, logged or sent anywhere but Anthropic's own endpoints.
