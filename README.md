# fahrma

> **fahrma** (FAR-mah): Austrian for "let's drive".

Shared cars run on trust. fahrma is a small, self-hosted cost tracker for cars shared by family, neighbours or friends. Log a trip in seconds on your phone, add the fuel receipt, and see who owes whom – to the cent, and traceable down to every single trip. No rental platform, no commission, no spreadsheet at the end of the month.

> Status: 0.3 – first public release. German and English interface. The features for hosting it for others are next on the [roadmap](#roadmap).

## Features

- **Trips in seconds:** start km is prefilled with the car's last reading. Start a trip now and finish it later, or enter it afterwards. Share a trip equally or by weights (2:1), and record money from passengers outside the group.
- **Fuel, charging and other costs:** fuel receipts with litres, charging with kWh, price per unit; insurance, tax, service, tyres, parking, toll and more, split by km, equally, to one person or like a specific trip.
- **Fair rate per km** per car and period, calculated from the actual fuel costs. Fuel without driven km carries over to the next period.
- **Settlements** freeze a period, show at most n−1 transfers, and let the people involved tick them off. Only the latest settlement can be undone.
- **Checks instead of surprises:** overlapping odometer readings are rejected, gaps are shown and must be confirmed, running trips block settling.
- **Groups with roles:** every person has their own login; admins add cars and invite others with a one-time link. Audit log of every change, CSV export.
- **German and English**, currency and time zone per group.
- **Installable web app** for iPhone, Android and desktop, light and dark.
- **Small footprint:** one container, one SQLite file, no external services.

How exactly it calculates: [docs/calculation.md](docs/calculation.md).

## Quick start

```bash
mkdir fahrma && cd fahrma
curl -fsSLO https://raw.githubusercontent.com/percuro/fahrma/main/compose.yaml
echo "PUBLIC_URL=https://cars.example.org" > .env
docker compose up -d && docker compose logs app   # shows the one-time setup token
```

Then point a TLS reverse proxy at `127.0.0.1:8000` and open `https://cars.example.org/setup`. Details: [docs/self-hosting.md](docs/self-hosting.md).

## Documentation

- [Self-hosting](docs/self-hosting.md): install, reverse proxy (Caddy, Traefik, Nginx Proxy Manager), updates, backup and restore
- [Configuration](docs/configuration.md): all environment variables
- [How it calculates](docs/calculation.md): rates, splits, rounding, transfers, with an example
- [Development](docs/development.md): running and testing from source
- [Design notes](docs/design.md): why it works the way it does

## Roadmap

- **0.4** ready to be hosted for others: open registration, e-mail (verification, password reset, invitations), account deletion and data export, group export and import between instances, operator links (imprint, privacy), limits
- **0.5** offline drafts (underground car parks), consumption and cost statistics per car
- **0.6** reservation calendar, reminders via Web Push
- **0.7** login via OpenID Connect
- **0.8** receipt photos
- **0.9** beta hardening; **1.0** stable API and configuration

## License

Source-available under the [PolyForm Noncommercial License 1.0.0](LICENSE) with an [addendum](LICENSE-ADDENDUM.md):

- **Free** for personal use and for non-profit organisations, including clubs and associations, also when they host it for their members.
- **Commercial use requires a license**: for example offering it as a paid hosted service or using it inside a company. See [COMMERCIAL.md](COMMERCIAL.md).

Contributions are welcome under the [Contributor License Agreement](CLA.md); see [CONTRIBUTING.md](CONTRIBUTING.md).
