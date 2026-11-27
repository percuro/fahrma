# Configuration

All settings are environment variables (for Docker Compose: the `.env` file next to `compose.yaml`). Only `PUBLIC_URL` is required.

An empty variable means its default. Switches take `true`/`false`, `on`/`off`, `yes`/`no` or `1`/`0`; numbers are whole numbers above 0. Any other value stops the start with a message naming the variable (see `docker compose logs app`), so a typo never turns a protection off silently.

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
| `SECURITY_LOG_DAYS` | `180` | How long the [security log](self-hosting.md#security-log) keeps an entry. |
| `INVITE_EXPIRY_DAYS` | `7` | How long invitation links stay valid. Password-reset links from an admin are valid for 24 hours, those requested by mail for 1 hour. |
| `IMPRINT_URL`, `PRIVACY_URL`, `TERMS_URL` | – | Links to the operator's imprint, privacy policy and terms of use, shown on the login, registration, invitation and profile pages. With `TERMS_URL` and open registration, new accounts must accept the terms. The texts themselves are yours to write and host. |
| `OIDC_ISSUER` | – (off) | Login through your own OpenID Connect provider (Authelia, Authentik, Pocket ID, Keycloak, …), in addition to passwords or instead of them. With `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` (or `OIDC_CLIENT_SECRET_FILE`), `OIDC_SCOPES`, `OIDC_LABEL` and `OIDC_AUTO_CREATE`; see [Login through your own provider](oidc.md). |
| `PASSWORD_LOGIN` | `on` | `off`: no passwords; accounts log in, register and are set up only through the provider. Needs `OIDC_ISSUER`. |
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
| `MAX_MEMBERS_PER_GROUP` | unlimited | Active members per group (also people without an account). Not together with `PLANS_FILE`: there, each plan has its own. |
| `MAX_CARS_PER_GROUP` | unlimited | Cars per group that are not archived. Not together with `PLANS_FILE`. |
| `MAX_RECEIPT_MB_PER_GROUP` | unlimited | Megabytes of receipt photos per group. Not together with `PLANS_FILE`. |
| `PLANS_FILE` | – | JSON file with the plans a group can have, each with its own limits; see [Plans](#plans). Unset: every group has the limits of `MAX_MEMBERS_PER_GROUP`, `MAX_CARS_PER_GROUP` and `MAX_RECEIPT_MB_PER_GROUP`. |
| `BILLING_URL` | – | Page where group admins change their group's plan (pricing page, contact form or your billing service); the group page then shows *Change plan*. See [Plans](#plans). |
| `OPERATOR_TOKEN` | – | Turns on the [operator API](operator-api.md) for your own tools, e.g. a billing service; at least 32 characters (`openssl rand -hex 32`). Also signs the billing links. |
| `OPERATOR_TOKEN_FILE` | – | Read the token from a file instead (e.g. a Docker secret); wins over `OPERATOR_TOKEN`. |
| `INACTIVE_DELETE_MONTHS` | – (never) | Delete accounts that have not been used for this many months (at least 3), after a warning; see [Deleting unused accounts](#deleting-unused-accounts). |
| `RECEIPTS` | on | Photos of receipts on fuel entries and expenses; `off` switches them off. See [Receipt photos](#receipt-photos). |
| `RECEIPTS_DIR` | `receipts` next to the database (`/data/receipts`) | Where the photos are stored. Required with a database that is not a SQLite file. |
| `MAX_RECEIPT_KB` | `3072` | Largest photo accepted, in KB (at least 100). The app shrinks photos to a few hundred KB before sending. |
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

## Plans

For hosting fahrma for others, each group can have a plan with its own limits – a free one and a paid one, say. fahrma contains no payment code: you decide outside the app who gets which plan and set it on the administration page (profile → *Instance administration* → *Groups*) or through the [operator API](operator-api.md).

```json
{
  "default": "free",
  "plans": [
    { "id": "free", "name": { "de": "Gratis", "en": "Free" }, "members_per_group": 5, "cars_per_group": 1, "receipt_mb_per_group": 50 },
    { "id": "plus", "name": "Plus", "members_per_group": 25, "cars_per_group": 5, "receipt_mb_per_group": 1000 },
    { "id": "club", "name": { "de": "Verein", "en": "Club" } }
  ]
}
```

- `id`: 1–32 characters `a-z`, `0-9`, `-`, `_`; stored with the group, so do not rename it once in use.
- `name`: one text, or one per language; shown to the group's members.
- `members_per_group`, `cars_per_group`, `receipt_mb_per_group` (megabytes of receipt photos): missing, `null` or `0` = unlimited.
- `default`: the plan of every group without its own – new groups, imported groups, groups whose plan ran out or was removed from the file.

A group's plan can have a last day (*valid until*, in the group's time zone); afterwards the default plan applies again. **Nothing is ever locked or deleted** when a plan ends or gets smaller: the group keeps every car, member and entry and works as before; only adding cars, members or photos beyond the limits of the plan now in force is refused, with a message that names the plan. A group moved in from another instance has to fit the default plan.

Changes to the file take effect without a restart. An invalid file stops the start with a message; if it becomes invalid while running, the plans read before stay in force and the error is logged. Plans and their limits are public (`/api/v1/meta`), so the app can show them.

With `BILLING_URL`, group admins see *Change plan* on the group page. It opens `BILLING_URL#group=<id>&plan=<current plan>` – and, with `OPERATOR_TOKEN`, `&token=<signed token>` that your billing service can check through the operator API, see [operator-api.md](operator-api.md#billing-links). The part after `#` never reaches access logs.

## Receipt photos

Members can attach up to five photos to each fuel entry and expense – the receipt, or the pages of a garage invoice. The app shrinks each photo on the phone to at most 1600 pixels on the longer side (a few hundred KB) and drops its metadata, such as where it was taken, before it is sent. Photos can be added to settled entries too; deleting them is only possible until the entry is settled, like changing it.

- The photos are files in `RECEIPTS_DIR` (`/data/receipts` in the container, on the same volume as the database), one directory per group. **Back them up with the database**: the SQL dump does not contain them, see [backup](self-hosting.md#backup-and-restore).
- They are only accepted as JPEG or WebP and only served to members of the group, with headers that keep a browser from running anything in them.
- Group → Data offers all photos of a group as a ZIP. The JSON export lists them, but a group moved to another instance arrives without its photos.
- Deleting an entry, a group or an account that takes its groups along removes the photos; leftovers of an interrupted upload are removed after an hour.
- With plans, `receipt_mb_per_group` limits the storage per group; the group page shows how much is used.

`RECEIPTS=off` hides them in the app and refuses new ones; photos already stored stay on disk until switched on again or deleted with their group.

## Deleting unused accounts

When you host fahrma for others, personal data should not stay forever. With `INACTIVE_DELETE_MONTHS=24`, say, an account nobody has used for 24 months is deleted exactly as if its owner had deleted it: login, name and e-mail address go, the trips and payments stay under an anonymous name in groups that have other members, and groups without other members are deleted with everything in them.

- **Warning:** 30 days before, by e-mail to the account's confirmed address. Using the app in between – any request with a valid login counts – cancels it. Accounts without an address (or without e-mail on the instance) are not warned but get the same 30 days after the moment they would have been, so switching the setting on never deletes anything on the same day.
- **Never deleted automatically:** instance admins, and accounts an admin deactivated (that is the admins' decision). People without an account are part of their groups and go with them.
- **When:** a round runs inside the app once an hour (the first a few minutes after the start). The administration page shows *will be deleted on …* for warned accounts, and the profile tells people the rule.
- **Before switching it on:** `python -m app.cli.inactive --months 24` counts what would be warned and deleted, without changing anything; `--run` runs one round now.

Say in your privacy policy how long unused accounts are kept.

## Limits

- Run exactly **one** instance with **one** worker process. State such as the first-run setup token and the login rate limits lives in memory, and SQLite is not meant for several writers across containers. One instance easily serves many groups.
- The app must be served at the root of its own (sub)domain; serving under a path like `/cars` is not supported.
- A request body may be at most 1 MB and must come with a `Content-Length` (browsers, curl and reverse proxies send one); the group import and receipt photos have their own limits. A larger body is refused with 413, one sent in chunks without a length with 411.
- Amounts are stored in cents of the group's currency, distances in whole kilometres. A group's currency can only be changed before its first amount; there is no conversion.
