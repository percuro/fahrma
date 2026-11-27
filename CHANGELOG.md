# Changelog

## 0.12.0-rc.1 – 2026-11-27

Beta hardening: a security log of logins and account changes, settings that no longer fail silently, updates tested from 0.3.0, signed images, and a more accessible, lighter app.

### Security log

- **Instance administration → Security:** logins and failed logins, wrong passwords when confirming a change, blocks by the rate limits, new and deleted accounts, passwords, e-mail addresses, devices logged out, links with the provider, roles, deactivations, instance invitations, password-reset links, plan changes and the warnings before unused accounts are deleted – also when they come from the command line, the operator API or the cleanup of unused accounts. Filter by account or to failed attempts only.
- **Your own account:** the profile shows *Recent security events* about your account, so you notice a login you do not know; an instance admin who acted stays unnamed. They are also in *My data*.
- IP addresses are stored only shortened (IPv4 /24, IPv6 /48) and only for failed attempts and blocks; a block is logged once. Passwords, tokens, links and usernames that do not exist are never stored. Usernames are copied, so entries stay readable after a deletion.
- Kept for `SECURITY_LOG_DAYS` (default 180 days). See [Security log](docs/self-hosting.md#security-log).
- `app.cli.stats` counts logins, failed attempts and blocks of the last 24 hours.

### Hardening

- **Settings are checked strictly.** A switch must be `true`/`false`, `on`/`off`, `yes`/`no` or `1`/`0`, a number a whole number above 0, `COOKIE_SAMESITE` one of `lax`, `strict` or `none`. Anything else stops the start with a message naming the variable. Before, `CSRF_PROTECTION=ture` silently turned CSRF protection off, and an invalid `SESSION_IDLE_MINUTES` meant the default.
- **Request size:** a request body may be at most 1 MB and must come with a `Content-Length`; the group import and receipt photos keep their own limits. Before, a large JSON body was read completely before it was refused.
- **Setup token:** five wrong tokens from anyone blocked the first-run setup for everyone for 15 minutes; they are now counted per IP address.
- **Operator API:** 20 wrong tokens from one address within 15 minutes block that address for a while (`429`).
- Stopping the container while a round of reminders, the cleanup of unused accounts or the receipt sweep is running no longer cuts it off; fahrma waits up to 10 seconds. `compose.yaml` gives the container 20 seconds to stop.

### Updates and images

- **Tested updates:** every change is tested by starting the 0.3.0 image and the previous release, adding a group with trips, fuel, an expense and a settlement, and starting the new image on the same volume. Rows, logins and the open balance must survive, and the updated instance must book, settle and restore its dump. You can update from any release since 0.3.0 straight to the newest one.
- Release images are built only after all checks have passed, and are **signed with cosign** in addition to the build provenance attestation. See [Verify the image](docs/self-hosting.md#verify-the-image).

### Accessibility

- After a change of page the focus moves to the start of the content and screen readers announce the new page, as after a page load.
- The instance administration is split into tabs (accounts, groups, invitations, security); tabs wrap instead of scrolling sideways on phones.
- An invalid or used invitation link now has a heading.
- The automatic WCAG 2.2 AA checks now also cover every tab of the administration, the expense, reservation and import forms, a form showing an error, the confirmation dialog, the pages without an account and the English interface. See [Accessibility](docs/accessibility.md).

### Performance

- The app start loads about a sixth less code (494 instead of 591 kB, 157 kB compressed): pages other than the start, the overview and the trip form load the first time they are opened. Offline use is unchanged; the app keeps all pages on the device.
- The group list of the instance administration and of the operator API reads all groups with a fixed number of queries instead of five per group.

### Upgrade notes

- **Check the log after the update** (`docker compose logs app`): a setting with a value that was silently ignored before now stops the start and names the variable.
- **Request size:** clients that send a body in chunks without a `Content-Length` get `411`; browsers, iOS shortcuts, curl and reverse proxies send one.
- Migration `0012` adds the table `security_events`. New optional setting `SECURITY_LOG_DAYS`.
- Optional: add `stop_grace_period: 20s` to your `compose.yaml`, as in the new one.
- The privacy policy should mention the security log: see the updated list in [hosting for others](docs/hosting-for-others.md#operator-information).
- API: new `GET /v1/admin/security-log` (`before_id`, `limit`, `user_id`, `failures`) and `GET /v1/account/security-log` (`before_id`, `limit`); *My data* has `security_log`. New error codes `request_too_large` and `length_required`; the operator API can answer `429 too_many_attempts`.

## 0.11.0 – 2026-11-27

Login through your own OpenID Connect provider: Authelia, Authentik, Pocket ID, Keycloak or any other, next to passwords or instead of them.

- **"Log in with …"** on the login page once `OIDC_ISSUER`, `OIDC_CLIENT_ID` and `OIDC_CLIENT_SECRET` are set; `OIDC_LABEL` names the button. Without `OIDC_ISSUER` nothing changes. See [Login through your own provider](docs/oidc.md).
- **Every way into an account works with the provider:** group invitations, personal links that take over a member without an account, instance invitations ("Continue with …"), open registration ("Register with …", with the terms as before), and the first-run setup. The link is used up only when the login succeeds.
- **Link an existing account** on the profile page under *Login*, confirmed with your password; afterwards both ways work. You can remove the link while a password remains. A password-reset link can link the account instead of setting a password.
- **Accounts without a password** confirm changes to their address and the deletion of their account with a login at the provider that is at most 10 minutes old; otherwise the app asks to *Confirm with …*. They can set a password later.
- **Remove password:** a linked account can give up its password (profile → *Login*), confirmed with a fresh login at the provider. It then logs in with the provider only – with passkeys or two factors there, that is the protection a password alone does not give. "Forgot password" by mail no longer applies to it; an instance admin can still create a reset link.
- **A new account takes the provider's address** if the provider has confirmed it and no other account uses it. Existing accounts keep managing their own.
- `OIDC_AUTO_CREATE=on` creates an account on the first login, for providers that already decide who may use fahrma. `PASSWORD_LOGIN=off` turns passwords off entirely.
- **Instance administration** shows who logs in with the provider and who has no password, and can remove an account's link (which logs it out everywhere). The devices list shows which logins came through the provider.
- `app.cli.stats` counts linked accounts and accounts without a password; *My data* contains the link.

### Security

- Authorization code flow with PKCE (S256). Only ID tokens signed with an asymmetric key of the provider are accepted (no HS256, no unsigned tokens); issuer, audience, `azp`, expiry, nonce and subject are checked, userinfo only counts for the same subject.
- Accounts are linked by issuer and subject, never by e-mail address.
- Every login is bound to the browser that started it (a cookie only for the callback path) and works once within 10 minutes; at most 30 starts per IP address in 15 minutes.
- Linking needs the password, so a stolen session cannot add a permanent way in. Removing the last way to log in is refused.
- Deleting an account also removes its link, so the provider account cannot log in to it again.
- "Forgot password" by mail does nothing for accounts without a password, so a mailbox cannot open an account that logs in with the provider only.

### Upgrade notes

- Migration `0011` adds the tables `oidc_identities` and `oidc_login_states` and the columns `auth_method` and `authenticated_at` to `user_sessions`; existing sessions count as password logins.
- New optional settings `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`/`OIDC_CLIENT_SECRET_FILE`, `OIDC_SCOPES`, `OIDC_LABEL`, `OIDC_AUTO_CREATE`, `PASSWORD_LOGIN`. The start is refused with `PASSWORD_LOGIN=off` but no provider, and with `OIDC_AUTO_CREATE=on` together with `TERMS_URL`.
- Register the redirect URI `https://<PUBLIC_URL>/api/v1/auth/oidc/callback` at the provider.
- API: `POST /v1/auth/oidc/start` (`login`, `register`, `link`, `reauth`), `GET /v1/auth/oidc/callback`, `POST /v1/invites/oidc`, `POST /v1/setup/oidc`, `DELETE /v1/account/oidc`, `DELETE /v1/account/password`, `DELETE /v1/admin/users/{id}/oidc`. `/v1/meta` has `password_login` and `oidc`, `/v1/auth/me` has `has_password` and `oidc`, admin users have `has_password` and `oidc_linked`, sessions have `auth_method`. `current_password` (password change) and `password` (address change, removing the address, account deletion) are optional for accounts without a password. New error codes `oidc_disabled`, `oidc_provider_unavailable`, `oidc_invalid_response`, `oidc_provider_error`, `oidc_denied`, `oidc_state_invalid`, `oidc_reauth_failed`, `oidc_no_account`, `oidc_already_linked`, `oidc_wrong_account`, `oidc_not_linked`, `oidc_not_for_link`, `reauth_required`, `password_login_disabled`, `last_login_method`, `no_password`.
- New dependency: `joserfc` (ID token checks).

## 0.10.0 – 2026-11-26

Receipt photos: a photo of the receipt on fuel entries and expenses, straight from the phone camera, with storage per plan.

- **Receipt photos:** up to five per fuel entry or expense – *Take photo* opens the camera, *Choose from photos* the library. The entry shows them as thumbnails, a tap opens them large; the history marks entries with a receipt.
- **Shrunk on the phone** before sending: at most 1600 pixels on the longer side, usually 150–400 KB. Re-encoding drops the photo's metadata, such as where it was taken.
- **Evidence, not amounts:** photos can still be added to a settled entry; deleting one is only possible until the entry is settled. Both are in the change log.
- **Without a connection** photos wait on the device with the entry's draft and are sent after it, never twice. Logging out or discarding the draft removes them.
- **Storage per plan:** `receipt_mb_per_group` in `PLANS_FILE`, or `MAX_RECEIPT_MB_PER_GROUP` without plans. The group page, the instance administration and the operator API show how much a group uses. A full group keeps every photo and only cannot add more until it deletes some or gets a bigger plan.
- **Your data:** Group → Data offers all photos as a ZIP, named by date, kind and entry. The JSON export lists them; a group moved to another instance arrives without its photos, and the import says so.
- `RECEIPTS=off` turns photos off; `RECEIPTS_DIR` and `MAX_RECEIPT_KB` set where they go and how large one may be. See [configuration](docs/configuration.md#receipt-photos).
- `app.cli.stats` counts receipts and their megabytes.
- Also in this release: the fix from 0.9.1 – date and time fields stay inside their card on iPhone and iPad.

### Security

- Photos are accepted only as JPEG or WebP, checked by their content, and served only to members of the group with their exact type, `nosniff` and a Content-Security-Policy that lets nothing in them run (`sandbox`).
- Files are removed only after the deletion of their entry, group or account is committed; an hourly cleanup removes leftovers of interrupted uploads and only ever touches files fahrma wrote itself.
- The app's Content-Security-Policy allows `blob:` images, for the preview of a photo before it is sent.

### Upgrade notes

- **Back up the photos:** they are files in `receipts/` on the data volume, next to the database, and **not** in the `app.cli.dump_sql` dump. Add the directory to your backup, see [self-hosting](docs/self-hosting.md#backup-and-restore).
- Migration `0010` adds the table `receipts`.
- New optional settings `RECEIPTS`, `RECEIPTS_DIR`, `MAX_RECEIPT_KB`, `MAX_RECEIPT_MB_PER_GROUP`; plans can have `receipt_mb_per_group`. Without them photos are on, stored next to the database, without a storage limit.
- API: fuel entries and expenses have `receipts`; new `POST /v1/groups/{id}/fuel/{id}/receipts` and `…/expenses/{id}/receipts` (the raw image as body, optional `Idempotency-Key`), `GET` and `DELETE /v1/groups/{id}/receipts/{id}`, `GET /v1/groups/{id}/receipts.zip`. `usage` and the plans have `receipt_mb_per_group`, `/v1/meta` has `receipts`, the import preview counts `receipts`. New error codes `receipt_too_large`, `receipt_invalid`, `receipt_type`, `receipt_count`, `receipt_not_found`, `receipts_off`; `limit_reached` can name `receipt_mb_per_group`.
- The image is based on Python 3.13.17.
- The roadmap moves: login via OpenID Connect is planned for 0.11.

## 0.9.1 – 2026-11-26

- Fixed: on iPhone and iPad, date and time fields stuck out of narrow forms on the right and showed their value centred. They now have the width of the other fields and start on the left; tapping still opens the picker.
- No migration, no new settings.

## 0.9.0 – 2026-11-26

Hosting fahrma for others: plans per group without payment code, and unused accounts deleted after a warning.

- **Plans per group** (`PLANS_FILE`): a free and a paid plan, say, each with its own limit of members and cars. The group page shows the group's plan, until when it is valid and what counts against it (*2 of 5 members*). Without `PLANS_FILE` nothing changes.
- **Change plan** (`BILLING_URL`): group admins go to the operator's pricing page or billing service, with the group's number in the address (after `#`, so it never reaches access logs) and, with `OPERATOR_TOKEN`, a signed token valid for an hour.
- **Instance administration → Groups:** every group with its plan, size, admins and last change – no trips, no amounts. Instance admins set a plan with a last day and a note for themselves (an invoice number, say), which the group never sees.
- **Operator API** (`OPERATOR_TOKEN`) for the operator's own billing service: list groups, set a group's plan, check a token from a billing link. See [operator-api.md](docs/operator-api.md).
- **Plans never lock anyone out:** when a plan runs out or gets smaller, the group falls back to the default plan and keeps everything; only adding cars or members beyond the limits is refused, and the message names the plan. A plan file that becomes invalid while running keeps the plans read before in force.
- **Deleting unused accounts** (`INACTIVE_DELETE_MONTHS`, off by default): accounts nobody has used for that many months are deleted like a deletion by their owner, after a warning by e-mail 30 days before; using the app in between keeps them. Instance admins and deactivated accounts are never deleted this way. The profile names the rule, the administration shows when a warned account goes, and `app.cli.inactive` counts what would happen before switching it on.
- `app.cli.stats` counts groups per plan and warned accounts.

### Security

- The operator API accepts only its bearer token (compared in constant time), never a login; without the token it does not exist (404). It sees plans and counts, never entries or amounts.
- Billing links are signed with a key derived from the operator token, valid for one hour, and only accepted while the person is still an admin of the group.
- The group export (`fahrma-group/1`) leaves the plan and the operator's note out: a plan belongs to the instance and does not move with a group.
- Fixed: deleting an account kept its e-mail address. It is removed now, and the migration removes it from accounts deleted earlier, so the address can also be used for a new account again.

### Upgrade notes

- Migration `0008` adds `plan`, `plan_until` and `plan_note` to `groups`; existing groups have the default plan.
- Migration `0009` adds `users.inactivity_warned_at` and removes the e-mail address of deleted accounts.
- New optional settings `PLANS_FILE`, `BILLING_URL`, `OPERATOR_TOKEN`/`OPERATOR_TOKEN_FILE`, `INACTIVE_DELETE_MONTHS`, see [configuration](docs/configuration.md#plans). With `PLANS_FILE`, set the limits per group in the file instead of `MAX_MEMBERS_PER_GROUP` and `MAX_CARS_PER_GROUP` (the start refuses both); `MAX_GROUPS_PER_USER` stays per account.
- API: `GET /v1/groups/{id}` has `plan`; `/v1/meta` has `plans`, `default_plan`, `billing` and `inactive_delete_months`; `/v1/admin/users` has `deletion_due`; new `POST /v1/groups/{id}/billing-link`, `GET /v1/admin/groups`, `PUT /v1/admin/groups/{id}/plan` and the operator routes under `/v1/operator/`. The error `limit_reached` has the parameter `plan` when plans are configured.
- The roadmap moves: login via OpenID Connect is planned for 0.10, receipt photos for 0.11.

## 0.8.0 – 2026-11-25

A new look, and one design language shared with pomale.

- **New look "night drive"**: ink blue and headlight amber, a dark top bar in the light and the dark scheme, a new app icon. People who have the app on their home screen see the new icon after adding it again.
- A **running trip** is a dark card at the top of the overview with its odometer reading as a large figure; your own balance is the large figure below.
- The **navigation** marks the active area with an amber pill. It sits at the bottom on phones and tablets and moves into the top bar from 840 px (before: 960 px).
- Edges of fields and buttons and the focus ring are clearly stronger (at least 3 : 1), the labels of the navigation grew to 12 px, dialogs open as a sheet from the bottom on a phone.
- On iPhone and iPad the text follows the system text size. The window title names the page ("New trip · fahrma").
- Styles are split into five layers (`frontend/src/styles/`), with one set of colour roles and components shared with pomale, see the [design language](docs/design-language.md). A test checks 40 colour pairs against the WCAG contrast minimum in both schemes; the end-to-end tests scan the main pages for WCAG 2.2 AA violations and for sideways scrolling at 320 px.
- Fixed: the link to a car's statistics on the overview had a name for screen readers that did not contain its visible text.
- Icons carry a version in their address (`/icon.svg?v=…`), so that browsers fetch a changed icon instead of showing the cached one for a week. Bookmarks pick up the new icon the next time the page is opened; some browsers only do so after the bookmark is added again.

### Upgrade notes

- No migration and no new settings. The roadmap moves by one version: login via OpenID Connect is planned for 0.9.

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
