# Security policy

## Supported versions

Only the latest release of vesha gets fixes.

## Reporting a vulnerability

Please **don't open a public issue**. Report it privately through
[GitHub's security advisories](https://github.com/Theyashsawarkar/vesha/security/advisories/new),
with what an attacker could do and how to reproduce it. You'll get a reply
within a week; a fix and a release follow as soon as it's confirmed, with
credit to you unless you'd rather not.

## What vesha handles

vesha runs as your user and manages Claude Code logins (OAuth tokens):

- Each login stays in its profile's `.credentials.json`, mode 0600, in a
  0700 folder; vesha's own state is 0600 too. vesha never copies, prints or
  logs a token.
- Tokens are sent only to Anthropic: `api.anthropic.com` (usage) and
  `platform.claude.com` (renewal), over HTTPS.
- The `claude` wrapper in `~/.local/bin` runs the first other `claude` on
  your PATH; anyone who can write to your PATH can already replace it.

Don't paste `.credentials.json`, tokens or `vesha doctor` output with your
emails into public issues.
