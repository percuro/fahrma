# Hosting for others

Running fahrma for your family is one thing; running it for people you do not know is another. This is a technical checklist for operators. It is not legal advice – what you need (imprint, privacy policy, a data processing agreement, terms) depends on your country and on whether you charge for it. Commercial hosting needs a commercial license: see [COMMERCIAL.md](../COMMERCIAL.md).

## Accounts and registration

- [ ] Decide how people get in. `REGISTRATION=invite` (default): only via invitation links from group admins or from you. `REGISTRATION=open`: anyone can register at `/register` (limited to 5 registrations per IP address and hour).
- [ ] Make sure at least two people you trust are instance admins (profile → *Instance administration*). If all admins are lost: `python -m app.cli.set_role <name> admin`.
- [ ] Set up e-mail ([configuration](configuration.md#e-mail)) so people can reset a forgotten password themselves and open registration confirms addresses. Use a sender domain with SPF and DKIM, otherwise the mails end up in spam. Without e-mail, people ask an admin for a reset link (valid 24 hours, once); say so in your help or FAQ.

## Operator information

- [ ] Publish an imprint, a privacy policy and terms of use on your own website and set `IMPRINT_URL`, `PRIVACY_URL` and `TERMS_URL`. They appear on the login, registration, invitation and profile pages. With open registration and `TERMS_URL`, new accounts must tick that they accept the terms.
- [ ] What the privacy policy should cover, from the app's side: accounts (username, display name, password hash, language, e-mail address if given), people without an account whom a group added (their name only), sessions (time of login and last activity, a coarse device name such as "iPhone · Safari"), the security log (logins, failed attempts and changes to accounts with the usernames involved, kept for `SECURITY_LOG_DAYS`, default 180 days; IP addresses only shortened to the network – IPv4 /24, IPv6 /48 – and only for failed attempts and blocks, to recognise attacks), group contents (cars, trips, fuel, costs, settlements, change log, receipt photos – shrunk and without location data), and your reverse proxy's and backups' own logs and retention.
- [ ] Set `INACTIVE_DELETE_MONTHS` (24, say) so that unused accounts do not stay forever, and name the period in your privacy policy. People are warned by mail 30 days before; check first with `python -m app.cli.inactive --months 24` ([details](configuration.md#deleting-unused-accounts)).
- [ ] People can download their data (profile → *My data*, JSON) and delete their account themselves. Deleting keeps their bookings in shared groups under an anonymous name, so the other members' balances stay correct – mention that in the privacy policy.

## Limits and plans

One instance carries many groups; you do not need an instance per customer. The group is the unit that has a plan.

- [ ] Simple caps for everyone: `MAX_GROUPS_PER_USER`, `MAX_MEMBERS_PER_GROUP`, `MAX_CARS_PER_GROUP` and `MAX_RECEIPT_MB_PER_GROUP`. Reaching a limit shows a clear message; archiving a car frees its place.
- [ ] Different limits per group – a free plan and a paid one: describe them in `PLANS_FILE` ([plans](configuration.md#plans)), storage for [receipt photos](configuration.md#receipt-photos) included, and keep `MAX_GROUPS_PER_USER` as a cap per account. Members see their group's plan and what counts against it on the group page.
- [ ] Decide how a group gets a bigger plan. By hand: set `BILLING_URL` to your pricing or contact page (it receives the group number), invoice outside the app, and set the plan with an end date under profile → *Instance administration* → *Groups*; the note field is for your invoice number. Automated: a billing service of your own behind `BILLING_URL` that checks the signed link and sets the plan through the [operator API](operator-api.md).
- [ ] Plans never lock anyone out: when a plan ends or gets smaller, groups keep everything and only cannot add beyond the new limits. Say so in your terms.
- [ ] Mention in your privacy policy what billing involves: the group number, the admin's name and confirmed e-mail address go to your billing service when someone changes the plan.
- [ ] `python -m app.cli.stats` prints numbers only (accounts, groups, groups per plan, entries per month) – useful for capacity planning without looking into anyone's data.

## Moving groups

- [ ] People can bring a group from another instance (Group → Data → *Complete as JSON* there, *Move a group here from another instance* here). The importing person becomes admin; everyone else becomes a person without an account until they use a personal link. Imports count against your limits and are capped at 20 MB. Receipt photos do not move along; people download them as a ZIP first.

## Operations

- [ ] TLS reverse proxy in front, the container port only reachable from the proxy, `PUBLIC_URL` with `https://`.
- [ ] Nightly backups with `app.cli.dump_sql` **and of the `receipts` directory**, kept off the server and encrypted, with a retention period that matches your privacy policy; test a restore regularly ([self-hosting.md](self-hosting.md#backup-and-restore)).
- [ ] Monitor `GET /api/health` and the backup job.
- [ ] With `OPERATOR_TOKEN`: keep it in a file (`OPERATOR_TOKEN_FILE`, e.g. a Docker secret), only in your billing service, and rotate it if it leaks (open billing links stop working then, which is harmless).
- [ ] Watch for new releases and read the [changelog](../CHANGELOG.md) before updating; pin image versions for deliberate updates.
- [ ] One instance, one worker: SQLite and the in-memory rate limits are built for that. A single small server carries many groups.

## What fahrma does not do (yet)

- No payment handling: fahrma knows plans and their limits, but who pays what is up to you, outside the app (see above).
- No notifications by mail about entries or settlements; reminders and news come by Web Push.
