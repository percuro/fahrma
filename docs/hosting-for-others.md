# Hosting for others

Running fahrma for your family is one thing; running it for people you do not know is another. This is a technical checklist for operators. It is not legal advice – what you need (imprint, privacy policy, a data processing agreement, terms) depends on your country and on whether you charge for it. Commercial hosting needs a commercial license: see [COMMERCIAL.md](../COMMERCIAL.md).

## Accounts and registration

- [ ] Decide how people get in. `REGISTRATION=invite` (default): only via invitation links from group admins or from you. `REGISTRATION=open`: anyone can register at `/register` (limited to 5 registrations per IP address and hour).
- [ ] Make sure at least two people you trust are instance admins (profile → *Instance administration*). If all admins are lost: `python -m app.cli.set_role <name> admin`.
- [ ] Without e-mail there is no self-service "forgot password": people ask an admin for a reset link (valid 24 hours, once). Say so in your help or FAQ.

## Operator information

- [ ] Publish an imprint, a privacy policy and terms of use on your own website and set `IMPRINT_URL`, `PRIVACY_URL` and `TERMS_URL`. They appear on the login, registration, invitation and profile pages. With open registration and `TERMS_URL`, new accounts must tick that they accept the terms.
- [ ] What the privacy policy should cover, from the app's side: accounts (username, display name, password hash, language), sessions (time of login and last activity, a coarse device name such as "iPhone · Safari"; no IP addresses are stored by the app), group contents (cars, trips, fuel, costs, settlements, change log), and your reverse proxy's and backups' own logs and retention.
- [ ] People can download their data (profile → *My data*, JSON) and delete their account themselves. Deleting keeps their bookings in shared groups under an anonymous name, so the other members' balances stay correct – mention that in the privacy policy.

## Limits

- [ ] Set `MAX_GROUPS_PER_USER`, `MAX_MEMBERS_PER_GROUP` and `MAX_CARS_PER_GROUP` if you want to cap usage (for example per plan). Reaching a limit shows a clear message; archiving a car frees its place.
- [ ] `python -m app.cli.stats` prints numbers only (accounts, groups, entries per month) – useful for capacity planning without looking into anyone's data.

## Operations

- [ ] TLS reverse proxy in front, the container port only reachable from the proxy, `PUBLIC_URL` with `https://`.
- [ ] Nightly backups with `app.cli.dump_sql`, kept off the server and encrypted, with a retention period that matches your privacy policy; test a restore regularly ([self-hosting.md](self-hosting.md#backup-and-restore)).
- [ ] Monitor `GET /api/health` and the backup job.
- [ ] Watch for new releases and read the [changelog](../CHANGELOG.md) before updating; pin image versions for deliberate updates.
- [ ] One instance, one worker: SQLite and the in-memory rate limits are built for that. A single small server carries many groups.

## What fahrma does not do (yet)

- No e-mail: no verification of addresses, no "forgot password" by mail (planned for 0.5).
- No payment handling: plans and billing are up to you, outside the app; limits can be set per instance.
- No import of groups from another instance yet (planned for 0.5; the JSON export already uses the format it will read).
