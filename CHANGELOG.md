# Changelog

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
