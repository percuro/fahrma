# Self-hosting

You need a Linux host with Docker and Docker Compose, a domain name pointing to it, and a reverse proxy that terminates TLS. HTTPS is required in practice: browsers only allow the service worker and "Add to Home Screen" on secure origins (and `localhost`), and login cookies are marked `Secure` for an `https://` address.

## Install

```bash
mkdir fahrma && cd fahrma
curl -fsSLO https://raw.githubusercontent.com/percuro/fahrma/main/compose.yaml
echo "PUBLIC_URL=https://cars.example.org" > .env
docker compose up -d
docker compose logs app
```

The log shows a block like this while no account exists:

```
No account exists yet. Open https://cars.example.org/setup and enter this setup token:

    3pX…

```

Open that address, enter the token, your name, a username and a password (at least 12 characters). The token is only valid until the first account exists. A restart without an account issues a new token; use the most recent one. Alternatively create the account on the command line:

```bash
docker compose exec app python -m app.cli.create_user alex --name "Alex"
```

Then create a group and a car in the app and invite the others with a link (page "Gruppe"). Everyone gets their own login; invitation links are valid for 7 days and can be used once.

The container listens on `127.0.0.1:8000` only. Put one of the following reverse proxies in front.

## Reverse proxy

### Caddy (simplest, automatic certificates)

On the host, `/etc/caddy/Caddyfile`:

```
cars.example.org {
    reverse_proxy 127.0.0.1:8000
}
```

Or as part of the same Compose project – remove the `ports:` section of the app and add:

```yaml
  caddy:
    image: caddy:2
    restart: unless-stopped
    ports: ["80:80", "443:443"]
    command: caddy reverse-proxy --from cars.example.org --to app:8000
    volumes:
      - caddy_data:/data
volumes:
  caddy_data:
```

### Traefik

Labels on the `app` service (remove `ports:`; the app must share a network with Traefik):

```yaml
    labels:
      - traefik.enable=true
      - traefik.http.routers.fahrma.rule=Host(`cars.example.org`)
      - traefik.http.routers.fahrma.entrypoints=websecure
      - traefik.http.routers.fahrma.tls.certresolver=letsencrypt
      - traefik.http.services.fahrma.loadbalancer.server.port=8000
```

### Nginx Proxy Manager

Add a proxy host for `cars.example.org` → scheme `http`, forward host `127.0.0.1` (or the app's container name if NPM shares a Docker network with it), port `8000`; request a Let's Encrypt certificate and enable "Force SSL". To share a network, add a `compose.override.yaml` next to `compose.yaml`:

```yaml
services:
  app:
    networks: [default, proxy]
networks:
  proxy:
    external: true
    name: <the network of your NPM container>
```

### Any other proxy

Forward everything to port 8000 and pass `Host`, `X-Forwarded-For` and `X-Forwarded-Proto`. No path rewriting, no special routes: the app serves both `/api` and the web interface.

## Updates

```bash
docker compose exec -T app python -m app.cli.dump_sql > backup-$(date +%F).sql   # backup first
docker compose pull
docker compose up -d
docker compose logs --tail=50 app
```

Database migrations run automatically when the container starts. The image tag `:0` follows all 0.x releases; pin a specific version (e.g. `:0.2.0`) if you prefer to update deliberately. Read the [changelog](../CHANGELOG.md) before updating.

You can update from any release since 0.3.0 straight to the newest one. Every change is tested that way: the 0.3.0 image and the previous release get a group with trips, fuel, an expense and a settlement, then the new image starts on the same volume and everything must still be there and work. Going back to an older release is only possible by restoring a backup.

### Verify the image

From 0.12 on, release images are signed with [cosign](https://docs.sigstore.dev/) by the release workflow (keyless, no key to manage) and carry a build provenance attestation:

```bash
cosign verify ghcr.io/percuro/fahrma:0.12.0 \
  --certificate-identity-regexp '^https://github.com/percuro/fahrma/.github/workflows/release.yml@refs/tags/v' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
gh attestation verify oci://ghcr.io/percuro/fahrma:0.12.0 --repo percuro/fahrma
```

Releases before 0.12 have the attestation but no signature.

### Upgrading to 0.4

The database is migrated automatically (`0003`). **The oldest active account becomes the admin of the instance**, all others become normal accounts; change roles on the new administration page (profile → *Instance administration*). Invitation links now carry their token after a `#` (`/invite#…`); links created before still work. Accounts deleted from now on stay as an anonymous name in their groups, so balances do not change.

### Upgrading to 0.3

The database is migrated automatically. If you use the API directly: the fuel field `liters_ml` is now called `quantity_milli`, and the paths of the web interface are English (old paths redirect).

### Upgrading from 0.1

Version 0.1 ran as two containers (backend and an nginx frontend). From 0.2 on there is a single image. The old variable names `PUBLIC_APP_URL` and `APP_TZ` still work but log a deprecation warning; rename them to `PUBLIC_URL` and `DEFAULT_TIMEZONE`. Note that the default time zone is now `UTC`; set `DEFAULT_TIMEZONE` (e.g. `Europe/Vienna`) to keep the previous behaviour. To keep the existing data volume, point the new `data` volume at it in a `compose.override.yaml`:

```yaml
volumes:
  data:
    external: true
    name: <old project name>_carshare_data
```

Invitation links from 0.1 (`/einladung/…`) keep working.

## Backup and restore

All data is on the `data` volume: one SQLite file, and the receipt photos in `receipts/` next to it. Create a consistent plain-SQL dump of the database while the app is running:

```bash
docker compose exec -T app python -m app.cli.dump_sql > fahrma.sql
```

The dump is uncompressed on purpose so that deduplicating backup tools such as restic or borg store only the changes. Example nightly cron job with restic:

```cron
30 3 * * * cd /srv/fahrma && restic backup --stdin-filename fahrma.sql --stdin-from-command -- docker compose exec -T app python -m app.cli.dump_sql
```

The dump does not contain the photos. Back up the `receipts` directory as well – the files never change once written, so an incremental backup stays small. With restic, for the compose project in `/srv/fahrma` (volume `fahrma_data`; `docker volume inspect fahrma_data` shows where it lives):

```cron
45 3 * * * restic backup /var/lib/docker/volumes/fahrma_data/_data/receipts
```

Restoring the photos means copying that directory back into the volume (owned by the container user, uid 10001). Photos whose entry is not in the restored database are removed after an hour; entries whose photo is missing show no picture.

Restore into an empty data volume (the command refuses to overwrite an existing database):

```bash
docker compose stop app
docker compose run --rm --no-deps app sh -c 'mv /data/carshare.db /data/carshare.db.before-restore 2>/dev/null; rm -f /data/carshare.db-wal /data/carshare.db-shm'
docker compose run --rm --no-deps -T app python -m app.cli.restore_sql < fahrma.sql
docker compose up -d
```

Test a restore now and then; a backup you never restored is a hope, not a backup.

## Account management

Accounts are normally created through invitation links: group admins invite people into their group, instance admins can invite people without a group and create password-reset links on the administration page (profile → *Instance administration*). With `REGISTRATION=open`, people can also register themselves. With your own OpenID Connect provider, people can log in there instead of with a fahrma password: through an invitation, the registration, by linking their account on the profile page, or automatically; see [Login through your own provider](oidc.md). Everyone can change their password, see and log out their devices, download their data and delete their account on the profile page.

From the command line:

```bash
docker compose exec app python -m app.cli.create_user <name> --name "Display name" [--role admin]
docker compose exec app python -m app.cli.create_user <name> --reset-password   # new password, logs out all devices
docker compose exec app python -m app.cli.set_role <name> admin                 # emergency exit if no admin is left
docker compose exec app python -m app.cli.stats                                 # numbers only, no content
```

### Security log

Instance admins find a security log on the administration page (tab *Security*): logins and failed logins, wrong passwords when confirming a change, blocks by the rate limits (login, setup token, invitation links, forgotten password, provider login, registration, operator API), new and deleted accounts, changed, set and removed passwords, confirmed and removed e-mail addresses, devices logged out, links with the OpenID Connect provider, roles, deactivations, instance invitations, password-reset links, changed plans and the warnings before unused accounts are deleted. Changes from the command line and from the operator API are marked as such. Filter by account or to failed attempts only.

- IP addresses are stored only shortened (IPv4 /24, IPv6 /48), and only for failed attempts and blocks. A block is logged once, not every refused request.
- Passwords, tokens and links are never stored, nor usernames that do not exist.
- The usernames involved are copied, so entries stay readable after an account is deleted.
- Entries are kept for `SECURITY_LOG_DAYS` (default 180) and then removed.
- Everyone sees the entries about their own account on the profile page (*Recent security events*), without the names of instance admins, and finds them in *My data*. Group contents and memberships are in each group's own change log instead.

`app.cli.stats` counts logins, failed attempts and blocks of the last 24 hours.

### Deleting accounts

Deleting an account removes its login, devices and name. Its trips and payments stay in its groups under an anonymous name ("Person 12"), also in frozen settlements, so the balances of the others stay correct. Groups without any other member are deleted with it; where it was the last group admin, the longest-standing member takes over.

## Monitoring

`GET /api/health` returns `{"status": "ok", "version": "…"}` when the app and its database work, otherwise HTTP 503. The image also defines a Docker health check.
