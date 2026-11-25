# Changelog

## 0.8.0-rc.1 – 2026-11-25

Release candidate of 0.8.0, for trying the new look on real devices.

A new look, and one design language shared with pomale.

- **New look "night drive"**: ink blue and headlight amber, a dark top bar in the light and the dark scheme, a new app icon. People who have the app on their home screen see the new icon after adding it again.
- A **running trip** is a dark card at the top of the overview with its odometer reading as a large figure; your own balance is the large figure below.
- The **navigation** marks the active area with an amber pill. It sits at the bottom on phones and tablets and moves into the top bar from 840 px (before: 960 px).
- Edges of fields and buttons and the focus ring are clearly stronger (at least 3 : 1), the labels of the navigation grew to 12 px, dialogs open as a sheet from the bottom on a phone.
- On iPhone and iPad the text follows the system text size. The window title names the page ("New trip · fahrma").
- Styles are split into five layers (`frontend/src/styles/`), with one set of colour roles and components shared with pomale, see the [design language](docs/design-language.md). A test checks 40 colour pairs against the WCAG contrast minimum in both schemes; the end-to-end tests scan the main pages for WCAG 2.2 AA violations and for sideways scrolling at 320 px.
- Fixed: the link to a car's statistics on the overview had a name for screen readers that did not contain its visible text.

## 0.7.0 – 2026-11-25

Reserving cars, and reminders on the phone.

- **Reservation calendar** (new tab *Calendar*): one week at a time, a list of days with who has which car; filter by car, and a free day opens a new reservation. Reserve a car for yourself or any member, also a person without an account, in steps of a quarter of an hour, with a note.
- Two reservations of the same car never overlap; the second one is refused with the name of whoever has the car then. Touching is fine (until 12:00, from 12:00).
- Times are wall-clock times in the group's time zone. A time skipped when the clocks go forward is refused, a time that happens twice when they go back means the first one.
- The person it is for, whoever entered it and the group admins can change or cancel a reservation, until it is over. Reservations of up to 31 days; archived cars cannot be reserved.
- The **overview** shows what is reserved now and next; **starting a trip** says when the car is booked for someone else right now. A reservation never blocks a trip.
- Reserving needs a connection (checking that the car is free is the point); offline the form says so.
- **Reminders by Web Push** (profile → *Notifications*), switched on per device: before your own reservation (15 minutes, 1 or 3 hours), when someone else reserves, moves or cancels for you, when your trip is still running after 12 hours or after your reservation, and on a new settlement. Each can be switched off; messages name people, cars and times, never amounts. A test message shows that it works.
- On iPhone and iPad (iOS 16.4 or later) notifications need the app on the home screen; the profile explains how.
- Leaving a group or deleting the account cancels upcoming reservations; past ones stay. Reservations move with a personal link and are part of the group export, the move between instances and *My data*. The bottom navigation has five areas now.

### Security

- Web Push needs no account with Google or Apple: the instance creates its own VAPID key on first use and keeps it in the database (so it is part of every backup). Every message is encrypted for the device (RFC 8291) and signed (RFC 8292); the push services only pass it on.
- The server only sends to the https addresses of known push services (Google, Mozilla, Apple, Microsoft; `PUSH_ALLOWED_HOSTS` adds more), never to an address a client hands in. Subscriptions the push service no longer knows are removed.
- A subscription belongs to a login: logging out, or out everywhere, ends it; when someone else logs in on the same browser, it moves to that account. Deleting the account removes subscriptions and settings.

### Upgrade notes

- Migrations `0006` (table `reservations`) and `0007` (`push_subscriptions`, `sent_notifications`, `instance_keys`, column `users.notify`) run automatically. Nothing changes for existing data.
- Web Push is on by default and needs outgoing HTTPS from the container to the push services. `PUSH=off` switches it off; `VAPID_SUBJECT` (default `PUBLIC_URL`, Apple wants `https://` or `mailto:`), `VAPID_PRIVATE_KEY_FILE` and `PUSH_DIR` are optional, see [configuration](docs/configuration.md#web-push). Reminders are checked once a minute inside the app; no cron job needed.
- API: new `GET/POST /v1/groups/{id}/reservations` (`?from=&to=&car_id=`), `GET/PUT/DELETE /v1/groups/{id}/reservations/{reservation_id}`, `GET/PUT /v1/account/notifications`, `POST/DELETE /v1/account/push-subscription`, `POST /v1/account/push-test`. `/v1/meta` has `vapid_public_key`. The group export (`fahrma-group/1`) has the optional key `reservations`; older files import as before.
- The image builds the frontend with Node 26.

## 0.6.0 – 2026-11-25

Working without a connection, and statistics per car.

- **Offline drafts:** a trip, a fuel or charging receipt, an expense or finishing a running trip that cannot reach the server is saved on the device and sent automatically once there is a connection again (app start, back online, back in view, every 30 seconds). The overview lists what has not been sent yet; a new trip starts at the odometer reading of a drafted one.
- **Starting without a connection:** the app opens offline with the last known group, members, cars and recent trips, so the forms work in an underground car park. Balances are never kept on the device; without a connection the overview says so.
- **Refused drafts** (e.g. a trip that overlaps one someone else entered meantime) stay on the overview with the reason; open them to correct or discard.
- **Statistics per car** (overview → *Statistics*, or a car's tile): km per month or year with chart and table, consumption full to full in l/100 km or kWh/100 km, cost per 100 km, average price per litre or kWh, costs by category and who drove how much. See [how it calculates](docs/calculation.md#statistics).
- A banner shows when the device is offline. Logging out warns about drafts that have not been sent and removes drafts and the kept data from the device.

### Security

- New entries are sent with an `Idempotency-Key`: a request repeated after a lost answer returns the entry saved the first time (status 200, header `Idempotent-Replayed: true`) instead of a copy. Keys are per group and person; an entry deleted since is not created again (`409 already_sent`).
- What the device keeps for offline use (`localStorage`) is limited to the account, the group with its members, the cars and the recent trips; it is removed when logging out or deleting the account, and when someone else logs in on the same device.

### Upgrade notes

- Migration `0005` runs automatically (table `idempotency_keys`). Nothing changes for existing data.
- API: `POST /v1/groups/{id}/trips`, `/fuel`, `/expenses` and `/trips/{id}/finish` accept an optional `Idempotency-Key` header (8–64 characters `A–Z a–z 0–9 _ -`). New: `GET /v1/groups/{id}/cars/{car_id}/stats?year=`.
- The new version of the app is offered as a reload as usual; drafts made with 0.5 do not exist, so there is nothing to migrate on the devices.

## 0.5.0 – 2026-11-25

Moving groups between instances, people without an account, and optional e-mail.

- **Move a group here** (profile or start page → *Move a group here from another instance*): upload the complete JSON export of another instance, see what it contains, pick which member you are, done. Every car, trip, fuel entry, expense, settlement, paid transfer and the change log arrive with new IDs and exactly the same numbers. The file is checked strictly first; nothing in it can refer to anything outside the new group. At most 20 MB; the instance's limits apply.
- **People without an account:** group admins can add someone by name only (*Add a person without an account*); the others record trips and payments for them. Imported groups bring every other member in this way. Admins can rename them.
- **Personal links:** *Link to take over* creates a one-time link for a person without an account. Whoever uses it becomes that member – with a new account, or with their existing one, which then takes over every booking in that group, including frozen settlements. Only the newest link works.
- **Optional e-mail** (`MAIL_FROM`, `SMTP_HOST`, …; see [configuration](docs/configuration.md#e-mail)):
  - *Forgot password?* on the login page sends a link (valid 1 hour) to the account's confirmed address, without revealing whether an account exists.
  - E-mail address in the profile, used once confirmed by a link; the previous address gets a notice.
  - Group invitations, personal links, invitations to the instance and password-reset links can also be sent by mail. An account that joins through a mailed link has that address confirmed.
  - With open registration the address is required and the account is created when the confirmation link is used.
  - Plain-text mails in German or English, sent after the response; at most 20 mails per account and hour, 3 reset mails per account and hour.
- Instance admins see confirmed addresses and can send a reset link by mail. `stats` counts people without an account separately.
- The group export marks people without an account (`placeholder`).

### Security

- People without an account cannot log in, never count as the admin a group needs, and are deleted with their group. A group whose only other members are people without an account is deleted with the last account, as before.
- E-mail addresses are checked strictly (no whitespace, so no header injection) and stored in lower case; a confirmation or reset link only works once and only the newest one per account.

### Upgrade notes

- Migration `0004` runs automatically (e-mail address and placeholder flag for accounts, personal links, pending confirmations). Nothing changes for existing data.
- E-mail stays off until you set `MAIL_FROM` and `SMTP_HOST`. With `REGISTRATION=open` and e-mail on, registration needs an address and returns `202` with `{"email": …}` instead of logging in right away.
- API: new `POST /v1/groups/import/check`, `POST /v1/groups/import?member=<id>` (the file as body), `POST /v1/groups/{id}/members`, `POST /v1/groups/{id}/members/{user_id}/invite`, `POST /v1/auth/forgot-password`, `POST`/`DELETE /v1/account/email`, `DELETE /v1/account/email/pending`. `POST /v1/groups/{id}/invites`, `POST /v1/admin/invitations` and `POST /v1/admin/users/{id}/password-reset` take an optional address (`email`, `send_email`). Members have `placeholder` and `link_expires_at`, `/v1/auth/me` has `email` and `email_pending`, `/v1/meta` has `mail`.

## 0.4.0 – 2026-11-25

Accounts, administration and data rights – what is needed to run fahrma for people you do not know.

- **Instance administration** (profile → *Instance administration*, for admins of the instance): list of accounts with role, status, number of groups and last activity – never trips or amounts. Make admin, deactivate (logs out everywhere), reactivate, delete, and create password-reset links. Admins never see or set passwords.
- **Invitations to the instance** without a group, optionally as admin, with a note; open links can be revoked.
- **Optional open registration** with `REGISTRATION=open` at `/register`, limited per IP address, impossible before the first-run setup.
- **Profile:** change the password (logs out the other devices), list of logged-in devices with log-out, *My data* as JSON, delete the own account.
- **Deleting an account** removes login, devices, username and display name – also from frozen settlements – and keeps the bookings under an anonymous name ("Person 12"), so the other members' balances do not change. Groups without any other member are deleted with it; where it was the last group admin, the longest-standing member takes over. The profile shows what will happen before confirming.
- **Groups:** delete a group (group admins, after typing its name); complete JSON export (`fahrma-group/1`) next to the CSV, as archive and as the basis for moving between instances in 0.5.
- **Operator links:** `IMPRINT_URL`, `PRIVACY_URL`, `TERMS_URL` are shown on the login, registration, invitation and profile pages; with open registration and `TERMS_URL` the terms must be accepted.
- **Limits** for hosted instances: `MAX_GROUPS_PER_USER`, `MAX_MEMBERS_PER_GROUP`, `MAX_CARS_PER_GROUP` (default unlimited).
- **CLI:** `create_user --role admin`, `set_role <name> admin|user` as an emergency exit, `stats` with numbers only.
- New guide [docs/hosting-for-others.md](docs/hosting-for-others.md).

### Security

- Invitation and reset links carry the token in the URL fragment (`/invite#…`), so it never reaches server or proxy logs; only a hash is stored, a link works once (atomically), wrong tokens are rate-limited per IP address.
- New usernames have 3–32 characters from `a–z 0–9 . _ -`; existing names stay valid.
- The device list stores a coarse device name from the User-Agent and the last activity, no IP addresses.
- A test calls every API route that takes an ID with another group's IDs and fails when a new route is missing from it.

### Upgrade notes

- Migration `0003` runs automatically. **The oldest active account becomes admin of the instance**; all others become normal accounts.
- Invitation links now look like `/invite#<token>`; links with the token in the path (`/invite/<token>`, `/einladung/<token>`) still work.
- API: `GET /v1/invites/{token}`, `POST /v1/invites/{token}/accept` and the token field of `POST /v1/auth/register` are replaced by `POST /v1/invites/inspect` and `POST /v1/invites/accept` (token in the body). `POST /v1/auth/register` is now the open registration. New: `/v1/meta`, `/v1/account/…`, `/v1/admin/…`, `DELETE /v1/groups/{id}`, `GET /v1/groups/{id}/export.json`. A deactivated account gets 401 `account_disabled` (was 403).

## 0.3.0 – 2026-11-25

- **New name: fahrma** (Austrian for "let's drive"; working name until now: Autokasse). Image `ghcr.io/percuro/fahrma`.
- **German and English interface.** Each person chooses the language in the new profile page, or it follows the browser. Error messages, settlement warnings and the CSV export follow the language.
- **Currency and time zone per group.** Admins set them in the group settings. The currency can only be changed before the first amount is entered; the time zone decides which day is "today" (default date of entries, latest settlement date) and falls back to `DEFAULT_TIMEZONE`.
- **Electric cars:** every car is combustion (litres) or electric (kWh). Fuel entries become fuel/charging entries with the matching unit and price per litre or kWh.
- **Amounts in any common notation:** "12,50", "12.50", "1.234,56" and "1,234.56" are all understood.
- **Interface polish:**
  - A short confirmation after saving, and Cancel in every form.
  - The app's own confirmation dialog instead of the browser's; removing a member and logging out now ask first.
  - Loading errors are shown with "Try again" instead of loading forever; unknown group addresses say so.
  - Touch targets of at least 44 px everywhere; the history tabs are real tabs, operable with arrow keys.
  - An expired session shows the login on top of the page, so the input is kept.
  - New trips and fuel entries preselect the car of your latest trip; the end km field gets the focus.
  - Expenses start with "Other" split equally instead of "Parking".
  - Profile page with name, language, groups and logout.
  - A notice with "Reload" when a new version is available.
  - Maskable app icon; browser colour for dark mode.
- English paths (`/g/1/trip/new`, `/history`, `/settlement` …); the German paths of earlier versions redirect.
- API: `GET` for single trips, fuel entries and expenses; `PATCH /groups/{id}` accepts `currency` and `timezone`; `PATCH /auth/me` accepts `locale`. **Breaking for API users:** the fuel field `liters_ml` is now `quantity_milli` (thousandths of the car's unit).
- Migration `0002` (runs automatically): language per user, time zone per group, energy unit per car, renamed fuel quantity column.

## 0.2.0 – 2026-11-24

First public release.

- **Single image:** FastAPI serves the API under `/api` and the web interface; the separate nginx container is gone. Security headers (CSP, HSTS for https, nosniff, frame deny) are set by the app.
- **First-run setup:** while no account exists, the log shows a one-time token; `/setup` creates the first account in the browser.
- **Configuration:** `PUBLIC_URL` is required and the only allowed origin for changes (plus optional `CORS_ORIGINS`); CSRF protection is on and cookies follow the scheme of `PUBLIC_URL` by default. New `DEFAULT_TIMEZONE` (default `UTC`), `FORWARDED_ALLOW_IPS`, `LOG_LEVEL`. `PUBLIC_APP_URL` and `APP_TZ` still work as deprecated aliases.
- **Error codes:** API errors and settlement warnings carry a stable `code` and `params` plus an English message; the interface translates them.
- Invitation links use `/invite/…`; old `/einladung/…` links redirect.
- CSV export in German or English (`?lang=de|en`), currency of the group in the header.
- Health check reports the version; the version is shown on the group page.
- English code, comments and documentation; license (PolyForm Noncommercial with addendum), contribution guidelines, CLA.
- Tests: ruff, new backend tests (setup, configuration, security headers, backups, error codes), Vitest for the frontend, Playwright end-to-end tests; CI and a release workflow that publishes multi-arch images to ghcr.io.

Upgrading from 0.1: see [docs/self-hosting.md](docs/self-hosting.md#upgrading-from-01).

## 0.1.1 – 2026-11-24

- API documentation (`/docs`, `/openapi.json`) only with `API_DOCS=true`

## 0.1.0 – 2026-11-24

- First version: groups with invitation links, cars, trips (running/finished, shared with weights, passenger payments), fuel entries, other costs with four ways of splitting
- Settlement per period with a rate per km per car, carry-over of fuel costs without km, gap and overlap checks of odometer readings, suggested transfers, tick off, undo the latest settlement
- Audit log, CSV export, SQL dump/restore for backups
- Installable web app, light and dark colour scheme
