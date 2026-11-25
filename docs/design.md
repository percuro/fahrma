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

## Not losing input

Entering a trip happens in car parks with poor reception and long gaps between uses. A login that expired in the meantime does not throw the form away: the login appears on top of the page, and after logging in the entry can be saved as it is.

## Accessibility

Large labelled touch targets, visible keyboard focus, state shown as text and not by colour alone, layouts that work with large text, and light and dark colour schemes following the system setting.
