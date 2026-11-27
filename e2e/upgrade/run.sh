#!/usr/bin/env bash
# Upgrade test: an instance of an earlier release gets data, then the new image starts on the same
# volume. Everything that existed must still be there and work.
#
#   e2e/upgrade/run.sh ghcr.io/percuro/fahrma:0.3.0 app:ci
#
# Creates data only with API calls that exist since 0.3.0 (joining a group falls back to the
# 0.3.0 way). ENGINE=podman for local runs; PORT (default 8000).
set -euo pipefail

FROM_IMAGE=${1:?usage: run.sh <old image> <new image>}
TO_IMAGE=${2:?usage: run.sh <old image> <new image>}
ENGINE=${ENGINE:-docker}
PORT=${PORT:-8000}
BASE="http://localhost:$PORT"
NAME=fahrma-upgrade
VOLUME=fahrma-upgrade-data
PASSWORD="upgrade-test-password-1"
SAM_PASSWORD="upgrade-test-password-2"

remove_instance() {
  $ENGINE rm -f "$NAME" >/dev/null 2>&1 || true
  $ENGINE volume rm -f "$VOLUME" >/dev/null 2>&1 || true
}
remove_instance
WORK=$(mktemp -d)
JAR="$WORK/cookies"
trap 'remove_instance; rm -rf "$WORK"' EXIT

log() { printf '\n== %s\n' "$*"; }

start() {
  # The command of every release, with the port configurable for local runs
  $ENGINE run -d --name "$NAME" --network host -v "$VOLUME:/data" \
    -e PUBLIC_URL="$BASE" -e PUSH=off -e RECEIPTS_DIR=/data/receipts "$1" \
    sh -c "alembic upgrade head && exec uvicorn app.web:application --host 127.0.0.1 --port $PORT" >/dev/null
  for _ in $(seq 1 60); do
    if curl -fsS "$BASE/api/health" >/dev/null 2>&1; then return 0; fi
    sleep 1
  done
  $ENGINE logs "$NAME"
  echo "$1 did not become healthy" >&2
  exit 1
}

stop() {
  $ENGINE stop -t 20 "$NAME" >/dev/null
  $ENGINE rm "$NAME" >/dev/null
}

# A JSON request with the session cookie and the CSRF header; prints the body, fails on HTTP errors
api() {
  local method=$1 path=$2 body=${3:-} jar=${4:-$JAR}
  local args=(-fsS -X "$method" -b "$jar" -c "$jar" -H "X-Carshare-CSRF: 1" -H "Origin: $BASE")
  if [ -n "$body" ]; then args+=(-H "Content-Type: application/json" --data "$body"); fi
  curl "${args[@]}" "$BASE/api$path"
}

json() { python3 -c "import json, sys; data = json.load(sys.stdin); print($1)"; }

# Rows by their columns that every release has, so a changed schema does not matter
snapshot() {
  $ENGINE exec -i "$NAME" python - <<'PY'
import sqlite3

db = sqlite3.connect("file:/data/carshare.db?mode=ro", uri=True)
queries = [
    "SELECT id, username, display_name, password_hash, is_active FROM users ORDER BY id",
    "SELECT id, name, currency, timezone FROM groups ORDER BY id",
    "SELECT group_id, user_id, role, active FROM memberships ORDER BY id",
    "SELECT id, name, plate, start_odometer_km, energy_unit, archived FROM cars ORDER BY id",
    "SELECT id, car_id, date, start_km, end_km, note, settlement_id FROM trips ORDER BY id",
    "SELECT trip_id, user_id, weight FROM trip_shares ORDER BY id",
    "SELECT trip_id, payer_name, amount_cents, received_by_user_id FROM trip_external_payments ORDER BY id",
    "SELECT id, car_id, date, odometer_km, quantity_milli, amount_cents, paid_by_user_id, settlement_id"
    " FROM fuel_entries ORDER BY id",
    "SELECT id, car_id, date, category, amount_cents, paid_by_user_id, allocation, settlement_id"
    " FROM expenses ORDER BY id",
    "SELECT id, period_start, period_end FROM settlements ORDER BY id",
    "SELECT settlement_id, from_user_id, to_user_id, amount_cents, paid_at FROM settlement_transfers ORDER BY id",
    "SELECT count(*) FROM audit_log",
]
for query in queries:
    print(db.execute(query).fetchall())
PY
}

day() { date -u -d "$1 days ago" +%F; }

log "Start $FROM_IMAGE"
start "$FROM_IMAGE"
token=$($ENGINE logs "$NAME" 2>&1 | grep -E '^    [A-Za-z0-9_-]{20,}$' | tail -1 | tr -d ' ')
test -n "$token"

log "Create data with $FROM_IMAGE"
api POST /v1/setup "{\"token\": \"$token\", \"username\": \"upgrade\", \"display_name\": \"Uli\", \"password\": \"$PASSWORD\"}" >/dev/null
api POST /v1/auth/login "{\"username\": \"upgrade\", \"password\": \"$PASSWORD\"}" >/dev/null
gid=$(api POST /v1/groups '{"name": "Upgrade family"}' | json 'data["id"]')
uli=$(api GET "/v1/groups/$gid" | json 'data["members"][0]["user_id"]')

# A second member through a group link: the current way, else the one of 0.3.0
invite=$(api POST "/v1/groups/$gid/invites")
invite_token=$(echo "$invite" | json 'data.get("token") or data["url"].rsplit("#", 1)[-1].rsplit("/", 1)[-1]')
sam_jar="$WORK/sam"
joined=$(curl -s -o /dev/null -w '%{http_code}' -X POST -c "$sam_jar" -H "X-Carshare-CSRF: 1" -H "Origin: $BASE" \
  -H "Content-Type: application/json" "$BASE/api/v1/invites/accept" \
  --data "{\"token\": \"$invite_token\", \"username\": \"sam\", \"display_name\": \"Sam\", \"password\": \"$SAM_PASSWORD\"}")
if [ "$joined" != 200 ]; then
  api POST /v1/auth/register \
    "{\"token\": \"$invite_token\", \"username\": \"sam\", \"display_name\": \"Sam\", \"password\": \"$SAM_PASSWORD\"}" \
    "$sam_jar" >/dev/null
fi
sam=$(api GET "/v1/groups/$gid" | json '[m["user_id"] for m in data["members"] if m["username"] == "sam"][0]')

car=$(api POST "/v1/groups/$gid/cars" '{"name": "Kombi", "plate": "UP-1", "start_odometer_km": 50000}' | json 'data["id"]')
api POST "/v1/groups/$gid/trips" "{\"car_id\": $car, \"date\": \"$(day 20)\", \"start_km\": 50000, \"end_km\": 50120,
  \"shares\": [{\"user_id\": $uli, \"weight\": 1}]}" >/dev/null
api POST "/v1/groups/$gid/trips" "{\"car_id\": $car, \"date\": \"$(day 15)\", \"start_km\": 50120, \"end_km\": 50400,
  \"note\": \"Urlaub\", \"shares\": [{\"user_id\": $uli, \"weight\": 1}, {\"user_id\": $sam, \"weight\": 2}],
  \"external\": [{\"payer_name\": \"Oma\", \"amount_cents\": 1000, \"received_by_user_id\": $sam}]}" >/dev/null
api POST "/v1/groups/$gid/fuel" "{\"car_id\": $car, \"date\": \"$(day 14)\", \"odometer_km\": 50400,
  \"quantity_milli\": 42000, \"amount_cents\": 6930, \"paid_by_user_id\": $sam}" >/dev/null
api POST "/v1/groups/$gid/expenses" "{\"car_id\": $car, \"date\": \"$(day 13)\", \"category\": \"insurance\",
  \"amount_cents\": 24000, \"paid_by_user_id\": $uli, \"allocation\": \"by_km\"}" >/dev/null
settlement=$(api POST "/v1/groups/$gid/settlements" "{\"period_end\": \"$(day 10)\", \"accept_warnings\": true}" | json 'data["id"]')
# Booked after the settlement: still open
open_trip=$(api POST "/v1/groups/$gid/trips" "{\"car_id\": $car, \"date\": \"$(day 5)\", \"start_km\": 50400, \"end_km\": 50450,
  \"shares\": [{\"user_id\": $sam, \"weight\": 1}]}" | json 'data["id"]')
balance_before=$(api GET "/v1/groups/$gid/balance" | json 'sorted((m["user_id"], m["balance_cents"]) for m in data["members"])' 2>/dev/null || echo none)
before=$(snapshot)
echo "$before"
stop

log "Upgrade to $TO_IMAGE"
start "$TO_IMAGE"
$ENGINE exec "$NAME" alembic current 2>&1 | tee "$WORK/current"
grep -q "(head)" "$WORK/current"
after=$(snapshot)
if [ "$before" != "$after" ]; then
  echo "Data changed by the upgrade" >&2
  diff <(echo "$before") <(echo "$after") >&2 || true
  exit 1
fi
echo "Rows unchanged"

log "Use the upgraded instance"
rm -f "$JAR" "$sam_jar"
api POST /v1/auth/login "{\"username\": \"upgrade\", \"password\": \"$PASSWORD\"}" >/dev/null
api POST /v1/auth/login "{\"username\": \"sam\", \"password\": \"$SAM_PASSWORD\"}" "$sam_jar" >/dev/null
# The oldest account became the instance admin (0.6), the group survived with both members
api GET /v1/auth/me | json 'data["role"]' | grep -qx admin
api GET "/v1/groups/$gid" | json 'sorted(m["username"] for m in data["members"])' | grep -q "'sam', 'upgrade'"
test "$(api GET "/v1/groups/$gid/trips" | json 'len(data)')" = 3
api GET "/v1/groups/$gid/settlements/$settlement" | json 'data["period_end"]' | grep -qx "$(day 10)"
balance_after=$(api GET "/v1/groups/$gid/balance" | json 'sorted((m["user_id"], m["balance_cents"]) for m in data["members"])' 2>/dev/null || echo none)
if [ "$balance_before" != none ] && [ "$balance_before" != "$balance_after" ]; then
  echo "Open balance changed: $balance_before -> $balance_after" >&2
  exit 1
fi
# Writing works: finish the open period with a new settlement, then undo it
api PUT "/v1/groups/$gid/trips/$open_trip" "{\"car_id\": $car, \"date\": \"$(day 5)\", \"start_km\": 50400,
  \"end_km\": 50460, \"shares\": [{\"user_id\": $sam, \"weight\": 1}]}" >/dev/null
second=$(api POST "/v1/groups/$gid/settlements" "{\"period_end\": \"$(day 1)\", \"accept_warnings\": true}" | json 'data["id"]')
api DELETE "/v1/groups/$gid/settlements/$second" >/dev/null
api GET /v1/admin/security-log | json 'len(data["events"])' >/dev/null

log "Dump and restore the upgraded instance"
$ENGINE exec "$NAME" sh -c 'python -m app.cli.dump_sql > /tmp/dump.sql'
$ENGINE exec "$NAME" sh -c 'python -m app.cli.restore_sql --target /tmp/restored.db < /tmp/dump.sql'
$ENGINE exec -i "$NAME" python - <<'PY'
import sqlite3

live = sqlite3.connect("file:/data/carshare.db?mode=ro", uri=True)
restored = sqlite3.connect("/tmp/restored.db")
query = "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
for (table,) in live.execute(query):
    counts = [db.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0] for db in (live, restored)]
    assert counts[0] == counts[1], f"{table}: {counts}"
print("The dump restores every row")
PY

log "Upgrade from $FROM_IMAGE passed"
