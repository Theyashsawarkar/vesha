# 8. Accounts and profiles live in the state folder

**Status:** Accepted  
**Date:** 2026-10-21  
**Amends:** [ADR 2](0002-one-profile-per-account.md), on where profiles live

## Context

v0.1.0 kept accounts and profiles in `~/.local/share/vesha`. That is also where installers put vesha itself: kosha installs every app into `~/.local/share/<name>`, and vesha's own `install.sh` clones there. The checkout and the logins can't share a folder: the clone would fail, or git would see the profiles as stray files, and removing the app could remove the logins.

## Decision

Accounts (`accounts.json`) and profiles live in `$XDG_STATE_HOME/vesha` (`~/.local/state/vesha`), next to the watcher's log. On first run, vesha moves them from the old folder, but only out of a folder that isn't a git checkout, and only when the new folder has no accounts yet.

## Consequences

- Installing, updating or removing vesha never touches a login.
- The move waits while a Claude Code session runs on one of the old profiles, so no running session loses its folder.
