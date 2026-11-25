# Configuration

All settings are environment variables (for Docker Compose: the `.env` file next to `compose.yaml`). Only `PUBLIC_URL` is required.

| Variable | Default | Description |
|---|---|---|
| `PUBLIC_URL` | – (required) | Address users open, e.g. `https://cars.example.org`. Must not contain a path. It is the only origin allowed to make changes (CSRF protection), it decides whether cookies are `Secure`, and invitation links are built from it. `PUBLIC_APP_URL` is accepted as a deprecated alias. |
| `DEFAULT_TIMEZONE` | `UTC` | Default IANA time zone that defines "today"; each group can set its own (default date of new entries, latest possible settlement date), e.g. `Europe/Berlin` or `America/New_York`. The server clock (usually UTC in containers) is never used for this. `APP_TZ` is accepted as a deprecated alias. |
| `DATABASE_URL` | `sqlite:////data/carshare.db` | SQLite database file. Keep it on the `/data` volume. Other databases are not supported. |
| `SESSION_IDLE_MINUTES` | `43200` (30 days) | A login expires after this much inactivity. Long on purpose: the home-screen web app on iOS has its own cookie storage, and frequent logins would get in the way of a quick entry at the parking spot. |
| `SESSION_ABSOLUTE_HOURS` | `2160` (90 days) | Maximum lifetime of a login. |
| `COOKIE_SECURE` | on for an `https://` `PUBLIC_URL` | Override only for special setups. |
| `COOKIE_SAMESITE` | `lax` | `lax`, `strict` or `none`. |
| `CSRF_PROTECTION` | `true` | Only disable for local experiments. |
| `CORS_ORIGINS` | – | Additional origins allowed to make changes, comma-separated. Rarely needed. |
| `FORWARDED_ALLOW_IPS` | `*` | Proxies whose `X-Forwarded-For`/`-Proto` headers are trusted. `*` is fine when the container port is only reachable through your reverse proxy (as in the provided `compose.yaml`). If the port is exposed, set it to your proxy's address. The login rate limit relies on the client address. |
| `REGISTRATION` | `invite` | `invite`: accounts only through invitation links (from a group admin, or from an instance admin on the administration page). `open`: anyone can register at `/register`; only possible after the first-run setup. Registrations are limited to 5 per IP address and hour. |
| `INVITE_EXPIRY_DAYS` | `7` | How long invitation links stay valid. Password-reset links from an admin are valid for 24 hours, those requested by mail for 1 hour. |
| `IMPRINT_URL`, `PRIVACY_URL`, `TERMS_URL` | – | Links to the operator's imprint, privacy policy and terms of use, shown on the login, registration, invitation and profile pages. With `TERMS_URL` and open registration, new accounts must accept the terms. The texts themselves are yours to write and host. |
| `MAIL_FROM` | – | Sender of e-mails, e.g. `fahrma <noreply@example.org>`. E-mail is optional and off unless `MAIL_FROM` and `SMTP_HOST` are set; see [E-mail](#e-mail). |
| `SMTP_HOST` | – | Mail server that accepts the mails for delivery (your provider's SMTP relay). |
| `SMTP_PORT` | `587` (`465` with `tls`, `25` with `none`) | Port of the mail server. |
| `SMTP_SECURITY` | `starttls` | `starttls` (port 587), `tls` (implicit TLS, port 465) or `none` (only for a relay on the same host). |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | – | Login at the mail server, if it needs one. |
| `SMTP_PASSWORD_FILE` | – | Read the password from a file instead (e.g. a Docker secret); wins over `SMTP_PASSWORD`. |
| `MAIL_DIR` | – | Development and tests: write each mail as an `.eml` file into this directory instead of sending it. |
| `PUSH` | on | Reminders by Web Push; `off` switches them off. Needs no account anywhere; see [Web Push](#web-push). |
| `VAPID_SUBJECT` | `PUBLIC_URL` | How push services can reach you: `mailto:ops@example.org` or an `https://` address. Apple refuses `http://` subjects. |
| `VAPID_PRIVATE_KEY_FILE` | – | Your own VAPID key (PEM, EC P-256). Unset: generated on first use and kept in the database. |
| `PUSH_ALLOWED_HOSTS` | – | Further push service hosts, comma-separated, besides those of Google, Mozilla, Apple and Microsoft. |
| `PUSH_DIR` | – | Development and tests: write each notification as a `.json` file into this directory instead of sending it. |
| `MAX_GROUPS_PER_USER` | unlimited | Active group memberships per account (creating and joining). Empty or `0` = unlimited. |
| `MAX_MEMBERS_PER_GROUP` | unlimited | Active members per group. |
| `MAX_CARS_PER_GROUP` | unlimited | Cars per group that are not archived. |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `API_DOCS` | `false` | `true` serves the OpenAPI documentation at `/api/docs`. Meant for development. |
| `FRONTEND_DIST` | `/app/frontend` in the image | Directory with the built frontend. Unset: API only (development with Vite). |

## E-mail

Without e-mail everything works with links that admins copy and pass on. With `MAIL_FROM` and `SMTP_HOST` set:

- **Forgot password:** the login page offers a link by mail to the account's confirmed address (valid 1 hour; at most 3 mails per account and hour). The answer never reveals whether an account or address exists.
- **Addresses:** everyone can enter an address in the profile; it counts once the link in the confirmation mail is used. The previous address gets a notice when it is replaced. Other members never see addresses; instance admins do.
- **Links by mail:** group invitations, personal links for people without an account, invitations to the instance and password-reset links can also be sent by mail. Every account can send at most 20 such mails per hour.
- **Open registration** (`REGISTRATION=open`) then asks for an address and creates the account only when the link in the mail is used (valid 2 days). Registering with an address that already has an account sends that account a hint instead.

Mails are plain text in the recipient's language, sent after the response; a failure is logged without the address. Test the setup by requesting a confirmation link for your own address in the profile.

```env
MAIL_FROM=fahrma <noreply@cars.example.org>
SMTP_HOST=smtp.example.org
SMTP_USERNAME=noreply@cars.example.org
SMTP_PASSWORD=…
```

## Web Push

Notifications work without configuration. On first use the instance creates a key pair (VAPID) and keeps it in the database, so it is part of every backup; a restored backup keeps the devices' subscriptions working. Losing the key only means everyone switches notifications on again.

- **What:** a reminder before the own reservation (15 minutes, 1 or 3 hours), a reservation someone else made, moved or cancelled for me, a trip still running after 12 hours or after the own reservation, and a new settlement. Everyone picks in the profile; the texts name people, cars and times, never amounts.
- **Where:** per device and login, switched on in the profile. Logging out ends it on that device. On iPhone and iPad (iOS 16.4 or later) only the app added to the home screen can receive notifications.
- **How:** messages are encrypted for the device and only go to the push services of the browsers (`fcm.googleapis.com`, `push.services.mozilla.com`, `push.apple.com`, `notify.windows.com`), never to an address a client hands in. The server needs outgoing HTTPS to them.
- **When:** reminders are checked once a minute inside the app; there is no separate worker or cron job.

## Limits

- Run exactly **one** instance with **one** worker process. State such as the first-run setup token and the login rate limits lives in memory, and SQLite is not meant for several writers across containers. One instance easily serves many groups.
- The app must be served at the root of its own (sub)domain; serving under a path like `/cars` is not supported.
- Amounts are stored in cents of the group's currency, distances in whole kilometres. A group's currency can only be changed before its first amount; there is no conversion.
