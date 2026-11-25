# Design notes

## What it is for

A handful of people share one or more private cars: family, neighbours, friends. Everyone records their trips (odometer readings), fuel receipts and other costs; the app works out who owes whom. The two moments that matter are entering something in a few seconds next to the car, and an occasional settlement that everyone can understand.

## Why a web app and no native apps

Recording a trip or a receipt is a short form. An installed web app (home screen on iOS and Android, or desktop) opens like an app, needs no app store, and one code base serves everyone who hosts it themselves. App stores would add fees, reviews and two more code bases without making these forms better. Web Push is available on iOS since 16.4 for installed web apps, so reminders do not require a native app either.

Native apps would only pay off for features a browser cannot offer well, such as reading the odometer with the camera in the background or detecting trips automatically. That is reconsidered after 1.0 if there is real demand; the React frontend would allow wrapping it with Capacitor.

## One container, SQLite

The image contains the API and the built frontend; FastAPI serves both. There is no separate web server, no database server and no cache. SQLite in WAL mode easily carries many small groups; the price is that exactly one instance runs. Backups are plain SQL dumps that deduplicating backup tools store efficiently.

## Exact money

Amounts are integer cents, distances whole kilometres. The calculation (`backend/app/services/settlement_engine.py`) works with exact fractions and rounds only once at the end, with the largest remainder method, so that the balances of a group always add up to exactly zero. How the numbers come about is described in [calculation.md](calculation.md).

## Settlements are frozen

A settlement freezes every entry up to its end date and stores a snapshot of its result. Later changes, a member leaving, or a new version of the calculation never change an old settlement. Only the latest settlement can be undone (by an admin), which makes its entries editable again. Every change is recorded in the audit log of the group.

## Languages and errors with codes

The interface is German and English; each person picks a language or follows the browser. All texts live in two typed dictionaries in the frontend, without a translation library. The API answers errors with a stable code and parameters, e.g. `{"code": "trip_overlap", "params": {"start_km": 10000, …}}`, and the interface turns them into text in the current language with local number and date formats. The server stays free of interface language; only the CSV export, which is a file people keep, is produced in the requested language.

## Deleting without breaking the books

A group's balances depend on every trip and payment of every member. Deleting an account therefore removes what identifies the person – login, devices, username, display name, also in frozen settlements – but keeps their bookings under an anonymous name. The others' balances and earlier settlements stay exactly as they were. Instance admins manage accounts, never contents: the administration page shows names, roles and activity, but no groups' trips or amounts.

## People without an account

Not everyone in a shared car wants an app: a grandmother, a teenager, a neighbour who drives twice a year. A group admin can add such a person by name; the others record their trips and payments, and the calculation treats them like any member. If the person wants to join later, a personal link lets them take over the place: a new account simply becomes that member, an existing account takes over every booking in that group, including the frozen settlements. Placeholders cannot log in, never count as the group's admin, and disappear with their group.

## Moving between instances

A group is not tied to the server it started on. The complete JSON export (`fahrma-group/1`) contains every row of the group; importing it on another instance renumbers everything – IDs in frozen settlement snapshots included – so the numbers stay exactly as they were. The file is checked strictly before anything is stored: every reference must point into the file, so an import can never touch another group. Whoever imports picks themselves among the members; everyone else becomes a person without an account until they use a personal link. This is what makes moving from self-hosting to a hosted service (and back) a matter of two clicks.

## E-mail is optional

Every link works without e-mail: an admin copies it and passes it on. With a mail server configured, the same links can go by mail, people confirm an address and get a new password themselves. Mails are plain text, sent after the response, and requests that start from an address answer the same whether it exists or not. An address only counts once its confirmation link was used, so a typo never locks anyone out or sends their reset links to a stranger.

## Links that do not leak

Invitation, password-reset and confirmation links carry their token after `#`. Browsers never send that part to the server, so it does not end up in access logs of the app or a reverse proxy. Only a hash of the token is stored, a link works once, and wrong tokens are rate-limited.

## Not losing input

Entering a trip happens in car parks with poor reception and long gaps between uses. A login that expired in the meantime does not throw the form away: the login appears on top of the page, and after logging in the entry can be saved as it is.

## Working without a connection

An underground car park is where trips end. The app starts there anyway: the service worker has the app itself, and the browser keeps what the forms need – the account, the group with its members, the cars and the recent trips. Balances and settlements are never kept on the device; amounts of money always come fresh from the server, and without a connection the overview says so instead of showing an old balance.

A new trip, a fuel receipt, an expense or finishing a running trip that cannot reach the server becomes a draft on the device. Drafts are listed on the overview and sent in the order they were made as soon as the server answers again – when the app starts, comes back online or into view, and every 30 seconds. The next trip already starts at the odometer reading of a drafted one.

A lost answer must not create a second entry: every draft carries a random key that goes with it as `Idempotency-Key`. The server remembers which entry a key created (per group and person), and a repeated request returns that entry instead of saving it again. If the server refuses a draft – it overlaps a trip someone else entered in the meantime, say – the draft stays with the reason, to be corrected or discarded. Logging out removes drafts and the kept data from the device, after a warning if something has not been sent.

## Accessibility

Large labelled touch targets, visible keyboard focus, state shown as text and not by colour alone, layouts that work with large text, and light and dark colour schemes following the system setting.
