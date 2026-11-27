# Security policy

## Reporting a vulnerability

Please report vulnerabilities **privately** via GitHub: on the repository page, open the **Security** tab and choose **Report a vulnerability**. Do not open a public issue.

Include what you found, how to reproduce it, and the version (`GET /api/health` shows it). You will get an answer within a week. Fixes are released as soon as possible and credited in the changelog unless you prefer otherwise.

## Supported versions

Only the latest release receives security fixes. Updating is a `docker compose pull && docker compose up -d` (see [docs/self-hosting.md](docs/self-hosting.md)).

## Scope notes

- The app is designed to run behind a TLS reverse proxy, with the container port bound to localhost.
- Login through an OpenID Connect provider accepts only asymmetrically signed ID tokens and links accounts by issuer and subject, never by e-mail address (see [docs/oidc.md](docs/oidc.md)).
- Rate limits and the first-run setup token are kept in memory; run a single instance (see [docs/configuration.md](docs/configuration.md#limits)).
- Logins, failed attempts, blocks and changes to accounts are kept in a security log for `SECURITY_LOG_DAYS` (default 180), with IP addresses only shortened and only for failed attempts and blocks (see [docs/self-hosting.md](docs/self-hosting.md#security-log)).
- Settings are checked strictly at startup: an unknown value for a switch such as `CSRF_PROTECTION` stops the start instead of meaning "off".
- Release images are built only after all checks pass and are signed with cosign (see [docs/self-hosting.md](docs/self-hosting.md#verify-the-image)).
