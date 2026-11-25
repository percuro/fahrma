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
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `API_DOCS` | `false` | `true` serves the OpenAPI documentation at `/api/docs`. Meant for development. |
| `FRONTEND_DIST` | `/app/frontend` in the image | Directory with the built frontend. Unset: API only (development with Vite). |

## Limits

- Run exactly **one** instance with **one** worker process. State such as the first-run setup token and the login rate limits lives in memory, and SQLite is not meant for several writers across containers. One instance easily serves many groups.
- The app must be served at the root of its own (sub)domain; serving under a path like `/cars` is not supported.
- Amounts are stored in cents of the group's currency, distances in whole kilometres. A group's currency can only be changed before its first amount; there is no conversion.
