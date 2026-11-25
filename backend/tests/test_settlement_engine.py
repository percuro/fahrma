import unittest
from fractions import Fraction

from app.services.settlement_engine import (
    EngineError,
    ExpenseInput,
    FuelInput,
    TripInput,
    calculate,
    minimal_transfers,
    round_balances,
    to_cents,
)

A, B, C = 1, 2, 3
CAR, CAR2 = 10, 20


class SimpleSplitTests(unittest.TestCase):
    def test_fuel_split_by_km(self):
        # 100 € fuel (A pays), A drives 300 km, B 100 km -> 25 ct/km -> A 75 €, B 25 €
        result = calculate(
            [A, B],
            trips=[TripInput(1, CAR, 300, {A: 1}), TripInput(2, CAR, 100, {B: 1})],
            fuel=[FuelInput(1, CAR, 10000, A)],
            expenses=[],
        )
        self.assertEqual(result.cars[CAR].rate, Fraction(25))
        self.assertEqual(result.members[A].balance_cents, 2500)
        self.assertEqual(result.members[B].balance_cents, -2500)
        self.assertEqual([(t.from_user_id, t.to_user_id, t.amount_cents) for t in result.transfers], [(B, A, 2500)])

    def test_shared_trip_split_by_weight(self):
        # 200 km together, A bears 1, B bears 3 shares; 60 € fuel (B pays) -> 30 ct/km
        result = calculate(
            [A, B],
            trips=[TripInput(1, CAR, 200, {A: 1, B: 3})],
            fuel=[FuelInput(1, CAR, 6000, B)],
            expenses=[],
        )
        self.assertEqual(result.members[A].km, Fraction(50))
        self.assertEqual(result.members[A].trip_cost, Fraction(1500))
        self.assertEqual(result.members[B].trip_cost, Fraction(4500))
        self.assertEqual(result.members[A].balance_cents, -1500)
        self.assertEqual(result.members[B].balance_cents, 1500)

    def test_external_payment_reduces_trip_cost_and_charges_receiver(self):
        # Trip 100 km at 30 ct = 30 €, a passenger pays A 20 €; B paid 30 € for fuel.
        # A: trip 30 - 20 credit + 20 held = 30 -> owes B 30 €, but has 20 € cash -> own share 10 €
        result = calculate(
            [A, B],
            trips=[TripInput(1, CAR, 100, {A: 1}, external=((A, 2000),))],
            fuel=[FuelInput(1, CAR, 3000, B)],
            expenses=[],
        )
        member_a = result.members[A]
        self.assertEqual(member_a.external_credit, Fraction(2000))
        self.assertEqual(member_a.external_held, Fraction(2000))
        self.assertEqual(member_a.balance_cents, -3000)
        self.assertEqual(result.members[B].balance_cents, 3000)

    def test_external_payment_on_shared_trip_benefits_all_participants(self):
        # Trip 30 € shared A/B, a passenger pays A 20 € -> A and B 5 € cost each, A holds 20 €
        result = calculate(
            [A, B, C],
            trips=[TripInput(1, CAR, 100, {A: 1, B: 1}, external=((A, 2000),))],
            fuel=[FuelInput(1, CAR, 3000, C)],
            expenses=[],
        )
        self.assertEqual(result.members[A].owed, Fraction(2500))
        self.assertEqual(result.members[B].owed, Fraction(500))
        self.assertEqual(result.members[C].balance_cents, 3000)

    def test_external_payment_received_by_non_participant(self):
        result = calculate(
            [A, B],
            trips=[TripInput(1, CAR, 100, {A: 1}, external=((B, 1000),))],
            fuel=[FuelInput(1, CAR, 3000, A)],
            expenses=[],
        )
        # A: paid 30, owes 30 - 10 = 20 -> +10. B: holds 10 € -> -10
        self.assertEqual(result.members[A].balance_cents, 1000)
        self.assertEqual(result.members[B].balance_cents, -1000)


class ExpenseAllocationTests(unittest.TestCase):
    def setUp(self):
        self.trips = [TripInput(1, CAR, 300, {A: 1}), TripInput(2, CAR, 100, {B: 1})]

    def test_equal_split_over_active_members(self):
        result = calculate([A, B, C], self.trips, fuel=[], expenses=[ExpenseInput(1, 9000, A, "equal")])
        self.assertEqual(result.members[A].balance_cents, 6000)
        self.assertEqual(result.members[B].balance_cents, -3000)
        self.assertEqual(result.members[C].balance_cents, -3000)

    def test_by_km_uses_car_km(self):
        result = calculate([A, B, C], self.trips, fuel=[], expenses=[ExpenseInput(1, 4000, C, "by_km", car_id=CAR)])
        self.assertEqual(result.members[A].expense_cost, Fraction(3000))
        self.assertEqual(result.members[B].expense_cost, Fraction(1000))
        self.assertEqual(result.members[C].balance_cents, 4000)

    def test_by_km_without_car_km_falls_back_to_group(self):
        result = calculate([A, B], self.trips, fuel=[], expenses=[ExpenseInput(1, 4000, A, "by_km", car_id=CAR2)])
        self.assertEqual(result.members[B].expense_cost, Fraction(1000))

    def test_by_km_without_any_km_is_carried_over(self):
        result = calculate([A, B], [], fuel=[], expenses=[ExpenseInput(1, 4000, A, "by_km")])
        self.assertEqual(result.carried_expense_ids, [1])
        self.assertEqual(result.included_expense_ids, [])
        self.assertEqual(result.members[A].balance_cents, 0)

    def test_single(self):
        result = calculate(
            [A, B], self.trips, fuel=[], expenses=[ExpenseInput(1, 1250, A, "single", allocated_user_id=B)]
        )
        self.assertEqual(result.members[B].balance_cents, -1250)

    def test_trip_allocation_uses_trip_shares(self):
        result = calculate(
            [A, B, C],
            self.trips,
            fuel=[],
            expenses=[ExpenseInput(1, 900, C, "trip", trip_shares={A: 2, B: 1})],
        )
        self.assertEqual(result.members[A].expense_cost, Fraction(600))
        self.assertEqual(result.members[B].expense_cost, Fraction(300))


class CarryOverAndMultiCarTests(unittest.TestCase):
    def test_fuel_without_km_is_carried_over(self):
        result = calculate(
            [A, B],
            trips=[TripInput(1, CAR, 100, {A: 1})],
            fuel=[FuelInput(1, CAR, 5000, B), FuelInput(2, CAR2, 4000, B)],
            expenses=[],
        )
        self.assertEqual(result.included_fuel_ids, [1])
        self.assertEqual(result.carried_fuel_ids, [2])
        self.assertEqual(result.cars[CAR2].carried_fuel_cents, 4000)
        self.assertEqual(result.members[B].balance_cents, 5000)

    def test_rates_are_per_car(self):
        result = calculate(
            [A, B],
            trips=[TripInput(1, CAR, 100, {A: 1}), TripInput(2, CAR2, 100, {B: 1})],
            fuel=[FuelInput(1, CAR, 2000, A), FuelInput(2, CAR2, 1000, A)],
            expenses=[],
        )
        self.assertEqual(result.cars[CAR].rate, Fraction(20))
        self.assertEqual(result.cars[CAR2].rate, Fraction(10))
        self.assertEqual(result.members[B].balance_cents, -1000)

    def test_trip_without_fuel_costs_nothing(self):
        result = calculate([A, B], trips=[TripInput(1, CAR, 100, {A: 1})], fuel=[], expenses=[])
        self.assertEqual(result.cars[CAR].rate, Fraction(0))
        self.assertEqual(result.members[A].balance_cents, 0)


class RoundingTests(unittest.TestCase):
    def test_balances_always_sum_to_zero(self):
        # 100 € among 3 people with odd km -> thirds of a cent
        result = calculate(
            [A, B, C],
            trips=[
                TripInput(1, CAR, 101, {A: 1}),
                TripInput(2, CAR, 103, {B: 1, C: 2}),
                TripInput(3, CAR, 7, {A: 1, B: 1, C: 1}, external=((C, 333),)),
            ],
            fuel=[FuelInput(1, CAR, 10000, A), FuelInput(2, CAR, 3333, B)],
            expenses=[ExpenseInput(1, 1000, C, "equal"), ExpenseInput(2, 777, A, "by_km")],
        )
        self.assertEqual(sum(m.balance_cents for m in result.members.values()), 0)
        transferred = sum(t.amount_cents for t in result.transfers)
        owed = sum(-m.balance_cents for m in result.members.values() if m.balance_cents < 0)
        self.assertEqual(transferred, owed)

    def test_round_balances_largest_remainder(self):
        third = Fraction(1, 3)
        self.assertEqual(
            round_balances({A: Fraction(100) + third, B: Fraction(-200) + third, C: Fraction(100) - 2 * third}),
            {A: 101, B: -200, C: 99},
        )
        self.assertEqual(round_balances({A: Fraction(1, 2), B: Fraction(-1, 2)}), {A: 1, B: -1})

    def test_to_cents_rounds_half_away_from_zero(self):
        self.assertEqual(to_cents(Fraction(5, 2)), 3)
        self.assertEqual(to_cents(Fraction(-5, 2)), -3)
        self.assertEqual(to_cents(Fraction(-6, 5)), -1)
        self.assertEqual(to_cents(Fraction(7)), 7)


class TransferTests(unittest.TestCase):
    def test_at_most_n_minus_one_transfers(self):
        transfers = minimal_transfers({1: 500, 2: -300, 3: -200, 4: 100, 5: -100})
        self.assertLessEqual(len(transfers), 4)
        net = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for t in transfers:
            net[t.from_user_id] -= t.amount_cents
            net[t.to_user_id] += t.amount_cents
        self.assertEqual(net, {1: 500, 2: -300, 3: -200, 4: 100, 5: -100})

    def test_nothing_to_transfer(self):
        self.assertEqual(minimal_transfers({1: 0, 2: 0}), [])


class ValidationTests(unittest.TestCase):
    def test_trip_without_shares_is_rejected(self):
        with self.assertRaises(EngineError):
            calculate([A], trips=[TripInput(1, CAR, 10, {})], fuel=[], expenses=[])


if __name__ == "__main__":
    unittest.main()
