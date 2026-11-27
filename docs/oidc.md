# Login through your own provider (OpenID Connect)

fahrma can let people log in through your own identity provider (Authelia, Authentik, Pocket ID, Keycloak, Zitadel, …) instead of, or in addition to, a fahrma password. It is optional: without `OIDC_ISSUER` nothing changes.

- **Exactly one provider** per instance.
- **Accounts are linked by the provider's issuer and subject (`sub`), never by e-mail address.** An address that happens to match an existing account does not give access to it.
- **Roles stay in fahrma.** The provider proves who someone is; instance admins and group admins are decided in fahrma. Groups from the provider are not used.
- **Logging out of fahrma does not log you out of the provider.**

## How it works

fahrma uses the authorization code flow with PKCE (S256) and checks the result strictly:

- The discovery document's `issuer` must equal `OIDC_ISSUER` (a trailing slash does not matter).
- The ID token must be signed with an asymmetric key the provider publishes: RS\*, PS\*, ES\* or EdDSA. Tokens signed with HS256 (the client secret) or unsigned are refused.
- `iss`, `aud` (and `azp` with several audiences), `exp`, `iat` (60 s leeway), `nonce` and `sub` are checked. Claims from the userinfo endpoint are only used if they name the same subject.
- Every login is bound to the browser that started it (a short-lived cookie) and can be used once, within 10 minutes.

fahrma reads `email`, `email_verified`, `preferred_username` and `name`: to show which provider account is linked, to suggest a username and a display name, and to give a **new** account the provider's address when the provider has confirmed it (`email_verified`) and no other account uses it. An existing account keeps managing its own address on the profile page.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `OIDC_ISSUER` | – (off) | The provider's issuer URL, e.g. `https://auth.example.org`. fahrma reads `<issuer>/.well-known/openid-configuration`. |
| `OIDC_CLIENT_ID` | – | Required with `OIDC_ISSUER`. |
| `OIDC_CLIENT_SECRET` | – | For a confidential client (recommended). Empty: public client, PKCE only. |
| `OIDC_CLIENT_SECRET_FILE` | – | Read the secret from a file instead (e.g. a Docker secret); wins over `OIDC_CLIENT_SECRET`. |
| `OIDC_SCOPES` | `openid profile email` | Must contain `openid`. |
| `OIDC_LABEL` | – | Name on the buttons, e.g. `Authelia` → "Log in with Authelia". Empty: "Log in with single sign-on". |
| `OIDC_AUTO_CREATE` | `off` | `on`: anyone who can log in at the provider gets an account (role user) on their first login. Use it when the provider already decides who may use fahrma (e.g. a group restriction on the client). Not together with `TERMS_URL`, see below. |
| `PASSWORD_LOGIN` | `on` | `off`: no passwords at all. Login, registration, invitations and the first-run setup work only through the provider. Needs `OIDC_ISSUER`. |

**Redirect URI** to register at the provider: `https://<your PUBLIC_URL>/api/v1/auth/oidc/callback`

**Client settings at the provider:** authorization code flow, PKCE S256, token endpoint authentication `client_secret_basic` (or `client_secret_post`, or `none` for a public client), scopes `openid profile email`, ID tokens signed with RS256 or another asymmetric algorithm.

fahrma does not contact the provider at startup; it starts even while the provider is down. If the provider uses a certificate from your own CA, mount the CA file into the container and set `SSL_CERT_FILE=/path/to/ca.pem`.

## Who gets an account

There are five ways to an account that logs in through the provider:

1. **Invitation.** Every kind of link works: a group invitation, a personal link that takes over a member without an account, and an instance invitation. The person enters a name and username and clicks "Continue with …". The link is used up only when the login succeeds.
2. **Registration** with `REGISTRATION=open`: the registration page offers "Register with …". The username is optional (fahrma suggests one from the provider). With `TERMS_URL`, the terms have to be accepted first, as with a password. The account exists right away; no confirmation mail is needed, because the provider vouches for the person.
3. **Linking an existing account.** Profile → *Login* → "Link with …", confirmed with the fahrma password. Afterwards both ways work.
4. **First-run setup.** The setup page offers "Continue with …"; the first admin account is then linked to the provider. With `PASSWORD_LOGIN=off` this is the only way.
5. **Automatically** with `OIDC_AUTO_CREATE=on`. The username comes from `preferred_username` or the e-mail address (a number is added if it is taken). fahrma refuses to start with `OIDC_AUTO_CREATE=on` and `TERMS_URL` together: an account created on its first login never accepts the terms. On a public instance with terms, use `REGISTRATION=open` instead.

**Accounts without a password** (created through the provider) confirm sensitive changes, such as changing the e-mail address, deleting the account or setting a password, with a login at the provider that is at most 10 minutes old. When it is older, fahrma shows "Confirm with …": the provider is asked for a fresh login (`prompt=login`) and fahrma checks `auth_time`. They can set a password on the profile page later while `PASSWORD_LOGIN=on`.

**Unlinking.** People can remove the link themselves only while a password remains. Instance admins can remove an account's link (administration → the account → *Remove link*); this logs the account out everywhere. Then create a password-reset link: with it the person sets a password, or links a provider account again ("Link with …").

**Changing `OIDC_ISSUER`** to another provider makes all existing links useless: the subjects belong to the old issuer. Link the accounts again (each person on the profile page, or with password-reset links).

**Locked out with `PASSWORD_LOGIN=off`** (provider gone)? Set `PASSWORD_LOGIN=on`, restart, and give the admin a password with `docker compose exec app python -m app.cli.create_user <name> --reset-password`.

## Provider examples

The examples assume fahrma at `https://cars.example.org`. The CI runs against Dex (`e2e/oidc/dex.yaml`).

### Authelia

```yaml
identity_providers:
  oidc:
    clients:
      - client_id: 'fahrma'
        client_name: 'fahrma'
        # authelia crypto hash generate pbkdf2 --variant sha512 --random --random.length 32
        client_secret: '$pbkdf2-sha512$310000$…'
        public: false
        authorization_policy: 'one_factor'   # or two_factor
        require_pkce: true
        pkce_challenge_method: 'S256'
        redirect_uris:
          - 'https://cars.example.org/api/v1/auth/oidc/callback'
        scopes: ['openid', 'profile', 'email']
        response_types: ['code']
        grant_types: ['authorization_code']
        token_endpoint_auth_method: 'client_secret_basic'
```

```env
OIDC_ISSUER=https://auth.example.org
OIDC_CLIENT_ID=fahrma
OIDC_CLIENT_SECRET=<the secret before hashing>
OIDC_LABEL=Authelia
```

Authelia sends the e-mail address and username only through the userinfo endpoint; fahrma reads it there.

### Authentik

Applications → Create with provider → **OAuth2/OpenID Provider**:

- Client type: **Confidential**. Redirect URI: `https://cars.example.org/api/v1/auth/oidc/callback` (strict).
- **Signing key: choose a certificate** (e.g. "authentik Self-signed Certificate"). Without one, Authentik signs ID tokens with HS256 and fahrma refuses them.
- Scopes: `openid`, `email`, `profile` (the defaults). Grant type: authorization code.
- Restrict who may use fahrma with a policy or group binding on the application if you use `OIDC_AUTO_CREATE=on`.

```env
OIDC_ISSUER=https://auth.example.org/application/o/<application slug>/
OIDC_CLIENT_ID=<client ID>
OIDC_CLIENT_SECRET=<client secret>
OIDC_LABEL=Authentik
```

### Pocket ID

Administration → OIDC Clients → Add OIDC Client: name `fahrma`, **Confidential client**, callback URL `https://cars.example.org/api/v1/auth/oidc/callback`. Then open the client:

- **Access → Allowed user groups:** new clients are restricted to groups. Choose **All Users** or add the groups that may use fahrma.
- Enable **PKCE**.

```env
OIDC_ISSUER=https://id.example.org
OIDC_CLIENT_ID=<client ID>
OIDC_CLIENT_SECRET=<client secret>
OIDC_LABEL=Pocket ID
```

### Any other provider

Register a web application (confidential client) with the redirect URI above and the scopes `openid profile email`, and set `OIDC_ISSUER` to the URL in front of `/.well-known/openid-configuration`.

## iPhone home-screen app

The home-screen app has its own cookie storage. The login at the provider opens inside the app and returns to it. This depends on iOS and the provider and has not been verified on a real device for every provider. If the app ends up in Safari instead, or you stay on the login page, use a fahrma password in the home-screen app (keep `PASSWORD_LOGIN=on` and set one on the profile page).

## Troubleshooting

The callback sends errors back into the app as a code in the address (`/login#error=…`, on the profile page for linking and confirming); the page shows them translated. The server log has the details (`OIDC login failed: …`).

| Code | Meaning |
|---|---|
| `oidc_provider_unavailable` | fahrma cannot reach the provider (DNS, TLS, firewall, `SSL_CERT_FILE`). |
| `oidc_invalid_response` | The provider's answer failed a check: wrong issuer, audience, signature (HS256?), or a wrong client secret or redirect URI. |
| `oidc_state_invalid` | The login took longer than 10 minutes, was finished in another browser, or reloaded after it was done. |
| `oidc_denied` / `oidc_provider_error` | The provider refused or the person cancelled. |
| `oidc_no_account` | No account is linked to this provider account and `OIDC_AUTO_CREATE` is off: send an invitation, or let the person link it on the profile page. |
| `oidc_already_linked` | The provider account is linked to another fahrma account. |
| `oidc_wrong_account` | A confirmation was done with a different provider account than the linked one. |
| `oidc_reauth_failed` | The provider did not ask for the login again although fahrma asked it to (`auth_time` too old). |
| `oidc_not_for_link` | Links that confirm an e-mail address or finish a registration by mail cannot be used with the provider. |
