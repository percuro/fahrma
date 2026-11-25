"""CSV export of all entries of a group.

German: semicolon and decimal comma (what Excel/LibreOffice expect in German locales).
English: comma and decimal point.
"""

import csv
import io

from sqlalchemy.orm import selectinload

from app.models.car import Car
from app.models.expense import Expense
from app.models.fuel import FuelEntry
from app.models.group import Membership
from app.models.trip import Trip
from app.models.user import User
from app.services.access import GroupContext

LANGUAGES = ("de", "en")

LABELS = {
    "de": {
        "header": [
            "Art", "Datum", "Auto", "Start-km", "End-km", "km", "Betrag {currency}", "Menge", "Einheit",
            "Bezahlt von", "Teilnehmer / Aufteilung", "Kategorie", "Notiz", "Abrechnung",
        ],
        "trip": "Fahrt", "fuel": "Tanken/Laden", "expense": "Kosten",
        "by_km": "nach km", "equal": "gleich", "trip_like": "wie Fahrt {id}", "single": "nur {name}",
        "external": "extern {payer} {amount} an {name}",
    },
    "en": {
        "header": [
            "Type", "Date", "Car", "Start km", "End km", "km", "Amount {currency}", "Quantity", "Unit",
            "Paid by", "Participants / split", "Category", "Note", "Settlement",
        ],
        "trip": "Trip", "fuel": "Fuel/charging", "expense": "Expense",
        "by_km": "by km", "equal": "equal", "trip_like": "like trip {id}", "single": "only {name}",
        "external": "external {payer} {amount} to {name}",
    },
}  # fmt: skip


def _sanitize(value) -> str:
    # Prevent formula injection in spreadsheet programs
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def export_csv(ctx: GroupContext, lang: str = "de") -> str:
    labels = LABELS[lang if lang in LABELS else "de"]
    decimal = "," if lang == "de" else "."

    def number(value: int | None, divisor: int) -> str:
        return "" if value is None else f"{value / divisor:.2f}".replace(".", decimal)

    gid = ctx.group.id
    names = dict(
        ctx.db.query(User.id, User.display_name)
        .join(Membership, Membership.user_id == User.id)
        .filter(Membership.group_id == gid)
        .all()
    )
    cars = dict(ctx.db.query(Car.id, Car.name).filter(Car.group_id == gid).all())
    units = dict(ctx.db.query(Car.id, Car.energy_unit).filter(Car.group_id == gid).all())
    rows: list[list] = []
    trips = (
        ctx.db.query(Trip)
        .options(selectinload(Trip.shares), selectinload(Trip.external_payments))
        .filter(Trip.group_id == gid)
        .all()
    )
    for t in trips:
        shares = ", ".join(f"{names.get(s.user_id, '?')} ×{s.weight}" for s in t.shares)
        external = "; ".join(
            labels["external"].format(
                payer=e.payer_name, amount=number(e.amount_cents, 100), name=names.get(e.received_by_user_id, "?")
            )
            for e in t.external_payments
        )
        rows.append([
            labels["trip"], t.date.isoformat(), cars.get(t.car_id), t.start_km, t.end_km,
            t.km if t.km is not None else "", "", "", "", "", shares, "",
            " · ".join(x for x in (t.note, external) if x), t.settlement_id or "",
        ])  # fmt: skip
    for f in ctx.db.query(FuelEntry).filter(FuelEntry.group_id == gid).all():
        rows.append([
            labels["fuel"], f.date.isoformat(), cars.get(f.car_id), f.odometer_km or "", "", "",
            number(f.amount_cents, 100), number(f.quantity_milli, 1000),
            units.get(f.car_id, "") if f.quantity_milli is not None else "",
            names.get(f.paid_by_user_id), labels["by_km"], "", f.note, f.settlement_id or "",
        ])  # fmt: skip
    for e in ctx.db.query(Expense).filter(Expense.group_id == gid).all():
        allocation = {
            "by_km": labels["by_km"],
            "equal": labels["equal"],
            "trip": labels["trip_like"].format(id=e.trip_id),
            "single": labels["single"].format(name=names.get(e.allocated_user_id, "?")),
        }[e.allocation]
        rows.append([
            labels["expense"], e.date.isoformat(), cars.get(e.car_id, ""), "", "", "",
            number(e.amount_cents, 100), "", "",
            names.get(e.paid_by_user_id), allocation, e.category, e.description, e.settlement_id or "",
        ])  # fmt: skip
    rows.sort(key=lambda r: (r[1], r[0]))
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";" if lang == "de" else ",")
    writer.writerow([column.format(currency=ctx.group.currency) for column in labels["header"]])
    for row in rows:
        writer.writerow([_sanitize(v) for v in row])
    return "﻿" + buffer.getvalue()  # BOM so that Excel detects UTF-8
