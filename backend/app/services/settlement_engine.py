"""Settlement engine: pure functions without a database.

Calculates exactly with Fraction and only rounds to cents at the end, so the sum
of all balances is always exactly 0.

Rules
- Rate per car = the car's fuel costs / the car's driven km in the period.
- A trip costs km x rate and is split by the participants' weights.
- An external payment X on a trip (e.g. a passenger outside the group) lowers the
  participants' cost by X (by weight); the person who received the money is charged X
  (they hold money of the group).
- Other expenses: by_km (km shares of the car, otherwise of the whole group), equal
  (active members), single (one person), trip (shares of the linked trip).
- Fuel costs of a car without km in the period, and by_km expenses without any km,
  are not settled but carried over to the next period.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from fractions import Fraction


@dataclass(frozen=True)
class TripInput:
    id: int
    car_id: int
    km: int
    shares: dict[int, int]  # user_id -> weight (>= 1)
    external: tuple[tuple[int, int], ...] = ()  # (received by user_id, cents)


@dataclass(frozen=True)
class FuelInput:
    id: int
    car_id: int
    amount_cents: int
    paid_by: int


@dataclass(frozen=True)
class ExpenseInput:
    id: int
    amount_cents: int
    paid_by: int
    allocation: str  # by_km | equal | single | trip
    car_id: int | None = None
    allocated_user_id: int | None = None
    # shares of the linked trip (only for allocation == "trip")
    trip_shares: dict[int, int] | None = None


@dataclass
class CarResult:
    car_id: int
    km: int = 0
    fuel_cents: int = 0
    rate: Fraction | None = None  # cents per km, None without km
    carried_fuel_cents: int = 0

    @property
    def rate_cents_per_km(self) -> float | None:
        return None if self.rate is None else float(self.rate)


@dataclass
class MemberResult:
    user_id: int
    km: Fraction = Fraction(0)
    paid_cents: int = 0
    trip_cost: Fraction = Fraction(0)
    external_credit: Fraction = Fraction(0)
    external_held: Fraction = Fraction(0)
    expense_cost: Fraction = Fraction(0)
    balance_cents: int = 0  # > 0: receives money, < 0: has to pay

    @property
    def owed(self) -> Fraction:
        return self.trip_cost - self.external_credit + self.external_held + self.expense_cost


@dataclass(frozen=True)
class Transfer:
    from_user_id: int
    to_user_id: int
    amount_cents: int


@dataclass
class EngineResult:
    cars: dict[int, CarResult]
    members: dict[int, MemberResult]
    transfers: list[Transfer]
    trip_costs: dict[int, Fraction]  # trip id -> cost before external payments (cents)
    included_trip_ids: list[int]
    included_fuel_ids: list[int]
    included_expense_ids: list[int]
    carried_fuel_ids: list[int] = field(default_factory=list)
    carried_expense_ids: list[int] = field(default_factory=list)


class EngineError(ValueError):
    pass


def _split(amount: Fraction, weights: dict[int, int]) -> dict[int, Fraction]:
    total = sum(weights.values())
    if total <= 0:
        raise EngineError("Split without weights")
    return {user_id: amount * weight / total for user_id, weight in weights.items()}


def round_balances(exact: dict[int, Fraction]) -> dict[int, int]:
    """Largest remainder: round to whole cents while keeping the exact sum (here 0)."""
    total = sum(exact.values(), Fraction(0))
    if total.denominator != 1:
        raise EngineError("Sum of balances is not a whole number of cents")
    floors = {user_id: value.numerator // value.denominator for user_id, value in exact.items()}
    missing = int(total) - sum(floors.values())
    # Largest fraction first, ties by smallest user_id (deterministic)
    order = sorted(exact, key=lambda uid: (-(exact[uid] - floors[uid]), uid))
    for user_id in order[:missing]:
        floors[user_id] += 1
    return floors


def minimal_transfers(balances: dict[int, int]) -> list[Transfer]:
    """Largest debtor pays largest creditor until everything is even (at most n-1 transfers)."""
    debtors = [[uid, -bal] for uid, bal in balances.items() if bal < 0]
    creditors = [[uid, bal] for uid, bal in balances.items() if bal > 0]
    transfers: list[Transfer] = []
    while debtors and creditors:
        debtors.sort(key=lambda item: (-item[1], item[0]))
        creditors.sort(key=lambda item: (-item[1], item[0]))
        debtor, creditor = debtors[0], creditors[0]
        amount = min(debtor[1], creditor[1])
        transfers.append(Transfer(debtor[0], creditor[0], amount))
        debtor[1] -= amount
        creditor[1] -= amount
        if debtor[1] == 0:
            debtors.pop(0)
        if creditor[1] == 0:
            creditors.pop(0)
    return transfers


def calculate(
    active_members: list[int],
    trips: list[TripInput],
    fuel: list[FuelInput],
    expenses: list[ExpenseInput],
) -> EngineResult:
    members: dict[int, MemberResult] = {}

    def member(user_id: int) -> MemberResult:
        if user_id not in members:
            members[user_id] = MemberResult(user_id)
        return members[user_id]

    for user_id in active_members:
        member(user_id)

    cars: dict[int, CarResult] = {}

    def car(car_id: int) -> CarResult:
        if car_id not in cars:
            cars[car_id] = CarResult(car_id)
        return cars[car_id]

    # km per car and per person (person: proportional to weight)
    car_member_km: dict[int, dict[int, Fraction]] = defaultdict(lambda: defaultdict(Fraction))
    for trip in trips:
        if trip.km < 0:
            raise EngineError(f"Trip {trip.id} has negative km")
        if not trip.shares:
            raise EngineError(f"Trip {trip.id} has no participants")
        car(trip.car_id).km += trip.km
        for user_id, km in _split(Fraction(trip.km), trip.shares).items():
            car_member_km[trip.car_id][user_id] += km
            member(user_id).km += km

    # fuel costs per car; without km: carried over
    included_fuel: list[int] = []
    carried_fuel: list[int] = []
    for entry in fuel:
        result = car(entry.car_id)
        if result.km == 0:
            result.carried_fuel_cents += entry.amount_cents
            carried_fuel.append(entry.id)
            continue
        result.fuel_cents += entry.amount_cents
        member(entry.paid_by).paid_cents += entry.amount_cents
        included_fuel.append(entry.id)
    for result in cars.values():
        if result.km > 0:
            result.rate = Fraction(result.fuel_cents, result.km)

    # trip costs + external payments
    trip_costs: dict[int, Fraction] = {}
    for trip in trips:
        rate = cars[trip.car_id].rate or Fraction(0)
        cost = rate * trip.km
        trip_costs[trip.id] = cost
        for user_id, part in _split(cost, trip.shares).items():
            member(user_id).trip_cost += part
        for receiver, cents in trip.external:
            if cents <= 0:
                raise EngineError(f"Trip {trip.id}: external payment must be positive")
            member(receiver).external_held += cents
            for user_id, part in _split(Fraction(cents), trip.shares).items():
                member(user_id).external_credit += part

    # other expenses
    group_km = {uid: m.km for uid, m in members.items() if m.km > 0}
    included_expenses: list[int] = []
    carried_expenses: list[int] = []
    for expense in expenses:
        amount = Fraction(expense.amount_cents)
        if expense.allocation == "by_km":
            weights: dict[int, Fraction] = {}
            if expense.car_id is not None:
                weights = {uid: km for uid, km in car_member_km.get(expense.car_id, {}).items() if km > 0}
            if not weights:
                weights = dict(group_km)
            if not weights:
                carried_expenses.append(expense.id)
                continue
            total = sum(weights.values(), Fraction(0))
            parts = {uid: amount * km / total for uid, km in weights.items()}
        elif expense.allocation == "equal":
            if not active_members:
                raise EngineError("No active members for an equal split")
            parts = _split(amount, {uid: 1 for uid in active_members})
        elif expense.allocation == "single":
            if expense.allocated_user_id is None:
                raise EngineError(f"Expense {expense.id}: person missing")
            parts = {expense.allocated_user_id: amount}
        elif expense.allocation == "trip":
            if not expense.trip_shares:
                raise EngineError(f"Expense {expense.id}: trip missing")
            parts = _split(amount, expense.trip_shares)
        else:
            raise EngineError(f"Unknown allocation {expense.allocation}")
        for user_id, part in parts.items():
            member(user_id).expense_cost += part
        member(expense.paid_by).paid_cents += expense.amount_cents
        included_expenses.append(expense.id)

    exact = {uid: Fraction(m.paid_cents) - m.owed for uid, m in members.items()}
    rounded = round_balances(exact)
    for uid, cents in rounded.items():
        members[uid].balance_cents = cents

    return EngineResult(
        cars=cars,
        members=members,
        transfers=minimal_transfers(rounded),
        trip_costs=trip_costs,
        included_trip_ids=[trip.id for trip in trips],
        included_fuel_ids=included_fuel,
        included_expense_ids=included_expenses,
        carried_fuel_ids=carried_fuel,
        carried_expense_ids=carried_expenses,
    )


def to_cents(value: Fraction) -> int:
    """Round to whole cents (half away from zero); only for displaying single items."""
    magnitude = int((abs(value) * 2 + 1) // 2)
    return magnitude if value >= 0 else -magnitude
