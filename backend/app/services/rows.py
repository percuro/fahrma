"""Plain dicts of database rows for the JSON exports."""

from datetime import date, datetime


def _value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def row_dict(row, exclude: frozenset[str] = frozenset()) -> dict:
    """All columns of an ORM object except ``exclude``, dates as ISO strings."""
    return {
        column.name: _value(getattr(row, column.key)) for column in row.__table__.columns if column.name not in exclude
    }
