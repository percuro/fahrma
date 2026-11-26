# Operator API

For your own tools around a hosted instance – typically a small billing service that sets a group's plan after payment. It is off unless `OPERATOR_TOKEN` (or `OPERATOR_TOKEN_FILE`) is set; see [configuration](configuration.md#plans).

- **Authentication:** `Authorization: Bearer <OPERATOR_TOKEN>` on every request. Logins and cookies are not accepted, not even an instance admin's, and the CSRF header is not needed. Without the token configured, every route answers `404 operator_api_disabled`; a wrong token gives `401 operator_unauthorized`.
- **What it sees:** plans, counts and the names of a group's admins – never trips, costs, amounts or settlements.
- **Where:** under `PUBLIC_URL/api/v1/operator/`. Call it from your server, not from a browser; keep the token out of anything that reaches users.

Errors have the same shape as everywhere else: `{"detail": {"code": "…", "message": "…", "params": {…}}}`.

## Groups

`GET /api/v1/operator/groups` lists every group, `?plan=<id>` only those with that plan stored. `GET /api/v1/operator/groups/{id}` returns one:

```json
{
  "id": 12,
  "name": "Familie Huber",
  "created_at": "2026-11-20T08:15:00",
  "last_activity_at": "2026-11-26T07:02:11",
  "plan": "plus",
  "plan_until": "2027-11-30",
  "plan_note": "Invoice 2026-017",
  "effective_plan": "plus",
  "usage": { "members_per_group": 4, "cars_per_group": 2 },
  "admins": [{ "user_id": 3, "display_name": "Anna" }]
}
```

`plan` is what is stored for the group (`null` = the default plan); `effective_plan` is the plan in force today, which differs once `plan_until` has passed or the plan was removed from `PLANS_FILE`. Times are UTC, `plan_until` is a day in the group's time zone (the last day the plan is valid).

## Setting a plan

```bash
curl -X PUT https://cars.example.org/api/v1/operator/groups/12/plan \
  -H "Authorization: Bearer $OPERATOR_TOKEN" -H "Content-Type: application/json" \
  -d '{"plan": "plus", "until": "2027-11-30", "note": "Invoice 2026-017"}'
```

The body replaces the group's plan: `plan` is an id from `PLANS_FILE` or `null` for the default plan (`422 plan_unknown` otherwise), `until` the last day or `null` for no end, `note` up to 200 characters for yourself – it is shown to instance admins, never to the group. The answer is the group as above. Setting the default plan clears `until`.

For a subscription, set `until` a few days after the paid period ends and move it on with every payment; if a payment stops, the group falls back to the default plan by itself, without losing anything (see [plans](configuration.md#plans)).

## Billing links

With `BILLING_URL` set, a group admin's *Change plan* opens

```
BILLING_URL#group=12&plan=free&token=eyJ2Ijox…
```

The token is signed with a key derived from `OPERATOR_TOKEN` and valid for one hour. It is not the operator token and does not work as one. Read it in the page's JavaScript (the part after `#` never reaches a server) and pass it to your backend, which checks it:

```bash
curl -X POST https://cars.example.org/api/v1/operator/billing-link/verify \
  -H "Authorization: Bearer $OPERATOR_TOKEN" -H "Content-Type: application/json" \
  -d '{"token": "eyJ2Ijox…"}'
```

```json
{
  "group": { "id": 12, "name": "Familie Huber", "effective_plan": "free", "…": "as above" },
  "user": { "user_id": 3, "display_name": "Anna", "email": "anna@example.org", "locale": "de" },
  "expires_at": "2026-11-26T09:12:40Z"
}
```

`email` is the person's confirmed address, if they have one. A token that is forged, changed or older than an hour gives `400 billing_token_invalid`; if the person is no longer an admin of the group (or the group is gone), `409 billing_not_admin`. Treat `group` and `plan` in the fragment as hints only – what counts is what `verify` returns.

A typical flow: verify the token, show the plans and start the checkout with your payment provider, keep the group id with the subscription, and on the provider's payment webhook call `PUT …/groups/{id}/plan`.
