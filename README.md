# fahrma

> **fahrma** (FAR-mah): Austrian for "let's drive".

Shared cars run on trust. fahrma is a small, self-hosted cost tracker for cars shared by family, neighbours or friends. Log a trip in seconds on your phone, add the fuel receipt, and see who owes whom – to the cent, and traceable down to every single trip. No rental platform, no commission, no spreadsheet at the end of the month.

> Status: 0.8 – a new look, with a design language shared with pomale. Ready to self-host for your family or club; see [hosting for others](docs/hosting-for-others.md) if you run it for people you do not know.

## Features

- **Trips in seconds:** start km is prefilled with the car's last reading. Start a trip now and finish it later, or enter it afterwards. Share a trip equally or by weights (2:1), and record money from passengers outside the group.
- **Fuel, charging and other costs:** fuel receipts with litres, charging with kWh, price per unit; insurance, tax, service, tyres, parking, toll and more, split by km, equally, to one person or like a specific trip.
- **Fair rate per km** per car and period, calculated from the actual fuel costs. Fuel without driven km carries over to the next period.
- **Works in the underground car park:** without a connection, entries are kept on the phone as drafts and sent automatically later – never twice. The app also starts offline.
- **Reservation calendar:** see who has which car when, reserve it for yourself or someone else; clashes are refused with the name of whoever has it.
- **Reminders on the phone** by Web Push: before your reservation, when someone books for you, when a trip is still running, on a new settlement. No app store, no account with Google or Apple, nothing to configure.
- **Statistics per car:** km per month, consumption full to full, cost per 100 km, price per litre or kWh, costs by category and who drove how much.
- **Settlements** freeze a period, show at most n−1 transfers, and let the people involved tick them off. Only the latest settlement can be undone.
- **Checks instead of surprises:** overlapping odometer readings are rejected, gaps are shown and must be confirmed, running trips block settling.
- **Groups with roles:** every person has their own login; admins add cars and invite others with a one-time link. People who do not want an account can be added by name; the others record for them, and a personal link lets them take over later. Audit log of every change, CSV and complete JSON export.
- **Move freely:** export a group as JSON and import it on another instance – self-hosted to hosted and back – with every entry and settlement intact.
- **Optional e-mail:** forgot password, confirmed addresses, invitations by mail, registration with address confirmation. Without it, everything works with links.
- **Your data stays yours:** change your password, see and log out your devices, download everything about you, or delete your account – your trips stay anonymously, so the others' balances keep adding up.
- **Instance administration:** accounts, roles, invitation and password-reset links – without seeing anybody's trips. Optional open registration, operator links (imprint, privacy, terms) and limits for hosting it for others.
- **German and English**, currency and time zone per group.
- **Installable web app** for iPhone, Android and desktop, light and dark.
- **Small footprint:** one container, one SQLite file, no external services (a mail server only if you want e-mail; push goes through the browsers' own services).

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
- [Hosting for others](docs/hosting-for-others.md): checklist when strangers use your instance
- [How it calculates](docs/calculation.md): rates, splits, rounding, transfers, with an example
- [Development](docs/development.md): running and testing from source
- [Design notes](docs/design.md): why it works the way it does
- [Design language](docs/design-language.md): the look, and the rules behind it

## Roadmap

- **0.9** login via OpenID Connect
- **0.10** receipt photos, beta hardening; **1.0** stable API and configuration

## Sibling project

[pomale](https://github.com/percuro/pomale) is a habit tracker by the same author: hosted the same way, under the same license, and built with the same [design language](docs/design-language.md) in a different character.

## License

Source-available under the [PolyForm Noncommercial License 1.0.0](LICENSE) with an [addendum](LICENSE-ADDENDUM.md):

- **Free** for personal use and for non-profit organisations, including clubs and associations, also when they host it for their members.
- **Commercial use requires a license**: for example offering it as a paid hosted service or using it inside a company. See [COMMERCIAL.md](COMMERCIAL.md).

Contributions are welcome under the [Contributor License Agreement](CLA.md); see [CONTRIBUTING.md](CONTRIBUTING.md).
