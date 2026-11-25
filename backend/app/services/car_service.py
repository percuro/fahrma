from fastapi import status
from sqlalchemy import func

from app.errors import AppError
from app.models.car import Car
from app.models.trip import Trip
from app.schemas.car import CarCreate, CarUpdate
from app.services.access import GroupContext
from app.services.audit_service import record
from app.services.limits import check_new_car


def get_car(ctx: GroupContext, car_id: int) -> Car:
    car = ctx.db.query(Car).filter(Car.id == car_id, Car.group_id == ctx.group.id).first()
    if car is None:
        raise AppError(status.HTTP_404_NOT_FOUND, "car_not_found", "Car not found")
    return car


def car_read(ctx: GroupContext, car: Car) -> dict:
    last_end = ctx.db.query(func.max(Trip.end_km)).filter(Trip.car_id == car.id).scalar()
    open_trip = ctx.db.query(Trip.id).filter(Trip.car_id == car.id, Trip.end_km.is_(None)).first()
    return {
        "id": car.id,
        "name": car.name,
        "plate": car.plate,
        "start_odometer_km": car.start_odometer_km,
        "energy_unit": car.energy_unit,
        "archived": car.archived,
        "last_km": max(last_end or 0, car.start_odometer_km),
        "open_trip_id": open_trip[0] if open_trip else None,
    }


def list_cars(ctx: GroupContext) -> list[dict]:
    cars = ctx.db.query(Car).filter(Car.group_id == ctx.group.id).order_by(Car.archived, Car.name).all()
    return [car_read(ctx, car) for car in cars]


def create_car(ctx: GroupContext, data: CarCreate) -> dict:
    ctx.require_admin()
    check_new_car(ctx.db, ctx.group.id)
    car = Car(group_id=ctx.group.id, **data.model_dump())
    ctx.db.add(car)
    ctx.db.flush()
    record(ctx, "car", car.id, "create", data.model_dump())
    ctx.db.commit()
    return car_read(ctx, car)


def update_car(ctx: GroupContext, car_id: int, data: CarUpdate) -> dict:
    ctx.require_admin()
    car = get_car(ctx, car_id)
    first_start = ctx.db.query(func.min(Trip.start_km)).filter(Trip.car_id == car.id).scalar()
    if first_start is not None and data.start_odometer_km > first_start:
        raise AppError(
            status.HTTP_409_CONFLICT,
            "car_start_after_trips",
            f"There are already trips from km {first_start}",
            km=first_start,
        )
    if car.archived and not data.archived:
        check_new_car(ctx.db, ctx.group.id)
    for key, value in data.model_dump().items():
        setattr(car, key, value)
    record(ctx, "car", car.id, "update", data.model_dump())
    ctx.db.commit()
    return car_read(ctx, car)
