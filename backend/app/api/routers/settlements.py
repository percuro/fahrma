from datetime import date

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.dependencies.clock import get_group_today
from app.api.dependencies.group import require_member
from app.config import APP_SLUG
from app.schemas.settlement import (
    BalanceRead,
    SettlementBrief,
    SettlementCreate,
    SettlementRead,
    TransferRead,
)
from app.services import balance_service, export_service
from app.services.access import GroupContext

router = APIRouter()


@router.get("/balance", response_model=BalanceRead)
def balance(
    period_end: date | None = Query(default=None),
    ctx: GroupContext = Depends(require_member),
    today: date = Depends(get_group_today),
):
    return balance_service.preview(ctx, period_end or today)


@router.get("/transfers/open", response_model=list[TransferRead])
def open_transfers(ctx: GroupContext = Depends(require_member)):
    return balance_service.open_transfers(ctx)


@router.post("/transfers/{transfer_id}/paid", response_model=TransferRead)
def mark_paid(transfer_id: int, ctx: GroupContext = Depends(require_member)):
    return balance_service.set_transfer_paid(ctx, transfer_id, True)


@router.delete("/transfers/{transfer_id}/paid", response_model=TransferRead)
def mark_unpaid(transfer_id: int, ctx: GroupContext = Depends(require_member)):
    return balance_service.set_transfer_paid(ctx, transfer_id, False)


@router.get("/settlements", response_model=list[SettlementBrief])
def list_settlements(ctx: GroupContext = Depends(require_member)):
    return balance_service.list_settlements(ctx)


@router.post("/settlements", response_model=SettlementRead, status_code=status.HTTP_201_CREATED)
def create_settlement(
    data: SettlementCreate, ctx: GroupContext = Depends(require_member), today: date = Depends(get_group_today)
):
    settlement = balance_service.create_settlement(ctx, data.period_end, today, data.accept_warnings)
    return balance_service.settlement_read(ctx, settlement)


@router.get("/settlements/{settlement_id}", response_model=SettlementRead)
def read_settlement(settlement_id: int, ctx: GroupContext = Depends(require_member)):
    return balance_service.settlement_read(ctx, balance_service.get_settlement(ctx, settlement_id))


@router.delete("/settlements/{settlement_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_settlement(settlement_id: int, ctx: GroupContext = Depends(require_member)):
    balance_service.delete_latest_settlement(ctx, settlement_id)


@router.get("/export.csv")
def export(
    lang: str = Query(default="de", pattern="^(de|en)$"),
    ctx: GroupContext = Depends(require_member),
    today: date = Depends(get_group_today),
):
    filename = f"{APP_SLUG}-{ctx.group.id}-{today.isoformat()}.csv"
    return Response(
        content=export_service.export_csv(ctx, lang),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
