from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies.group import require_member
from app.schemas.car import CarCreate, CarRead, CarUpdate
from app.schemas.stats import CarStats
from app.services import car_service, stats_service
from app.services.access import GroupContext

router = APIRouter()


@router.get("", response_model=list[CarRead])
def list_cars(ctx: GroupContext = Depends(require_member)):
    return car_service.list_cars(ctx)


@router.post("", response_model=CarRead, status_code=status.HTTP_201_CREATED)
def create_car(data: CarCreate, ctx: GroupContext = Depends(require_member)):
    return car_service.create_car(ctx, data)


@router.put("/{car_id}", response_model=CarRead)
def update_car(car_id: int, data: CarUpdate, ctx: GroupContext = Depends(require_member)):
    return car_service.update_car(ctx, car_id, data)


@router.get("/{car_id}/stats", response_model=CarStats)
def car_stats(
    car_id: int,
    year: int | None = Query(default=None, ge=1900, le=2200),
    ctx: GroupContext = Depends(require_member),
):
    return stats_service.car_stats(ctx, car_id, year)
