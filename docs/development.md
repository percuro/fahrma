# Development

```
backend/    FastAPI, SQLAlchemy 2, Alembic, unittest   (Python 3.13)
frontend/   React 19, TypeScript, Vite, TanStack Query, Vitest
e2e/        Playwright end-to-end tests against a running instance
Dockerfile  single image: builds the frontend, serves it and the API (/api) with uvicorn
```

| Where | What |
|---|---|
| `backend/app/services/settlement_engine.py` | The calculation: pure functions without a database, exact with `Fraction` |
| `backend/app/services/balance_service.py` | Loads entries, runs the engine, creates and undoes settlements |
| `backend/app/errors.py` | `AppError`: every intended error has a stable `code` and `params` |
| `frontend/src/i18n/de.ts`, `en.ts` | All interface texts, including those for error codes and settlement warnings |
| `frontend/src/lib/format.ts` | Formatting by language and group currency, tolerant parsing of typed numbers |
| `frontend/src/app/brand.ts`, `backend/app/config.py` | Product name (see [renaming.md](renaming.md)) |

Units: money in integer cents of the group's currency, distances in whole km, fuel quantities in thousandths of the car's unit (ml or Wh).

## Backend

```bash
python3.13 -m venv .venv && .venv/bin/pip install -r backend/requirements-dev.txt
cd backend
export DATABASE_URL=sqlite:///./carshare.db PUBLIC_URL=http://localhost:5173 DEFAULT_TIMEZONE=Europe/Berlin
../.venv/bin/alembic upgrade head
../.venv/bin/uvicorn app.web:application --reload --port 8000   # prints a setup token
```

Set `API_DOCS=true` to get the OpenAPI documentation at `http://localhost:8000/api/docs`. To try e-mail without a mail server, set `MAIL_FROM=fahrma <noreply@example.org>` and `MAIL_DIR=/tmp/fahrma-mail`: every mail lands there as an `.eml` file.

Tests and checks:

```bash
../.venv/bin/python -m unittest discover -s tests -v
../.venv/bin/ruff check . && ../.venv/bin/ruff format --check .
```

Database changes: edit the models in `app/models/`, then `../.venv/bin/alembic revision --autogenerate -m "…"` and review the generated file in `alembic/versions/`. CI checks that the migrations match the models (`alembic check`).

## Frontend

```bash
cd frontend
npm ci
npm run dev      # http://localhost:5173, proxies /api to the backend on :8000
npm test         # Vitest
npm run lint
npm run build
```

`PUBLIC_URL` must be the address in the browser (`http://localhost:5173` with the Vite dev server), otherwise changes are rejected by the CSRF protection.

## End-to-end tests

Against the built image (like CI):

```bash
docker build -t app:dev .
docker run -d --name app-e2e -p 8000:8000 -e PUBLIC_URL=http://localhost:8000 app:dev
export E2E_SETUP_TOKEN=$(docker logs app-e2e 2>&1 | grep -E '^    [A-Za-z0-9_-]{20,}$' | tail -1 | tr -d ' ')
cd e2e && npm ci && npx playwright install chromium webkit
E2E_BASE_URL=http://localhost:8000 npx playwright test
```

The mail tests need an instance that writes its mails to a directory the tests can read: start the container with `-e "MAIL_FROM=fahrma <noreply@example.org>" -e MAIL_DIR=/mail -v /tmp/mail:/mail` (the directory writable for the container, e.g. `mkdir -m 777 /tmp/mail`) and set `E2E_MAIL_DIR=/tmp/mail`. Without it they are skipped.

Without Docker, run `uvicorn app.web:application` with `FRONTEND_DIST=../frontend/dist` (after `npm run build`) and a fresh database instead. The first run creates the account through the setup page; later runs log in (`E2E_USERNAME`/`E2E_PASSWORD`, defaults in `e2e/global-setup.ts`). Every test creates its own group, so tests do not depend on each other.

## Conventions

- English for code, comments, docs and commit messages.
- Interface texts live in `frontend/src/i18n/de.ts` (the reference) and `en.ts`; TypeScript and `i18n.test.ts` report missing keys. No text in components.
- Errors the API raises on purpose use `AppError(status, code, english_message, **params)`. Add a text for every new code to both language files.
- Formatting goes through `useFormat()` (language and group currency), never through hard-coded locales.
- Never change the result of an existing settlement: settled entries are frozen, and the calculation of a settlement is stored as a snapshot.
- "Today" comes from the group's time zone or `DEFAULT_TIMEZONE` through the `Clock` dependency (`app/api/dependencies/clock.py`), never from the server clock. Tests replace it with `FixedClock`.
