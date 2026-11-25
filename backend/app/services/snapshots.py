"""Renumbering the IDs inside a frozen settlement snapshot.

A snapshot (see balance_service._serialize) refers to people, cars and trips by ID. When a
group moves to another instance, or a placeholder member is merged into an account, the
IDs change while the numbers must stay exactly as they were.
"""

import json


class SnapshotError(ValueError):
    """The snapshot refers to an ID that is not in the mapping."""


def _mapped(mapping: dict[int, int], value, where: str, strict: bool):
    if value is None:
        return None
    if isinstance(value, int) and value in mapping:
        return mapping[value]
    if strict:
        raise SnapshotError(where)
    return value


def remap_snapshot(
    snapshot: dict,
    users: dict[int, int],
    cars: dict[int, int] | None = None,
    trips: dict[int, int] | None = None,
) -> dict:
    """A copy of the snapshot with new IDs.

    Without cars/trips only people are renumbered and other IDs stay. With a mapping, every
    ID of that kind must be in it (SnapshotError otherwise), except trip costs of trips that
    no longer exist, which are dropped.
    """
    data = json.loads(json.dumps(snapshot))
    full = cars is not None
    for index, member in enumerate(data.get("members") or []):
        member["user_id"] = _mapped(users, member.get("user_id"), f"members[{index}].user_id", full)
    for index, transfer in enumerate(data.get("transfers") or []):
        for key in ("from_user_id", "to_user_id"):
            transfer[key] = _mapped(users, transfer.get(key), f"transfers[{index}].{key}", full)
    if cars is not None:
        for index, car in enumerate(data.get("cars") or []):
            car["car_id"] = _mapped(cars, car.get("car_id"), f"cars[{index}].car_id", True)
        for warning in data.get("warnings") or []:
            if "car_id" in warning:
                warning["car_id"] = _mapped(cars, warning.get("car_id"), "warnings.car_id", True)
    if trips is not None and isinstance(data.get("trip_costs"), dict):
        costs = {}
        for key, cost in data["trip_costs"].items():
            try:
                old = int(key)
            except ValueError:
                continue
            if old in trips:
                costs[str(trips[old])] = cost
        data["trip_costs"] = costs
    return data


def dumps(snapshot: dict) -> str:
    return json.dumps(snapshot, default=str, ensure_ascii=False)
