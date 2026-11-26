"""Receipt photos of fuel entries and expenses.

Every member may attach and delete photos, like entries. Attaching also works after the entry
was settled (a photo changes no amount); deleting only before, like changing the entry itself.
"""

import io
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Literal

from fastapi import status
from sqlalchemy import select

from app.config import receipts_enabled
from app.errors import AppError
from app.models.expense import Expense
from app.models.fuel import FuelEntry
from app.models.receipt import MAX_RECEIPTS_PER_ENTRY, RECEIPT_TYPES, Receipt
from app.services import entry_service, idempotency, receipt_store
from app.services.access import GroupContext
from app.services.audit_service import record
from app.services.limits import check_receipt_space
from app.services.receipt_image import InvalidImage, image_size

EntryKind = Literal["fuel", "expense"]


def require_enabled() -> None:
    if not receipts_enabled():
        raise AppError(status.HTTP_404_NOT_FOUND, "receipts_off", "Receipt photos are turned off on this instance")


def _entry(ctx: GroupContext, kind: EntryKind, entry_id: int) -> FuelEntry | Expense:
    if kind == "fuel":
        return entry_service.get_fuel(ctx, entry_id)
    return entry_service.get_expense(ctx, entry_id)


def get_receipt(ctx: GroupContext, receipt_id: int) -> Receipt:
    receipt = ctx.db.scalar(select(Receipt).where(Receipt.id == receipt_id, Receipt.group_id == ctx.group.id))
    if receipt is None:
        raise AppError(status.HTTP_404_NOT_FOUND, "receipt_not_found", "Receipt not found")
    return receipt


def add(
    ctx: GroupContext, kind: EntryKind, entry_id: int, data: bytes, content_type: str, key: str | None = None
) -> tuple[Receipt, bool]:
    """Attach a photo; returns the receipt and whether it was created by an earlier request with ``key``."""
    require_enabled()
    if (earlier := idempotency.previous(ctx, key, "receipt")) is not None:
        return idempotency.load(ctx, earlier, get_receipt), True
    entry = _entry(ctx, kind, entry_id)
    if content_type not in RECEIPT_TYPES:
        raise AppError(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "receipt_type",
            "Send a JPEG or WebP image",
            types=list(RECEIPT_TYPES),
        )
    try:
        width, height = image_size(data, content_type)
    except InvalidImage:
        raise AppError(status.HTTP_422_UNPROCESSABLE_CONTENT, "receipt_invalid", "This is not a usable image") from None
    if len(entry.receipts) >= MAX_RECEIPTS_PER_ENTRY:
        raise AppError(
            status.HTTP_409_CONFLICT,
            "receipt_count",
            f"At most {MAX_RECEIPTS_PER_ENTRY} photos per entry",
            max=MAX_RECEIPTS_PER_ENTRY,
        )
    check_receipt_space(ctx.db, ctx.group.id, len(data))
    file = receipt_store.save(ctx.group.id, data, RECEIPT_TYPES[content_type])
    try:
        receipt = Receipt(
            group_id=ctx.group.id,
            fuel_id=entry.id if kind == "fuel" else None,
            expense_id=entry.id if kind == "expense" else None,
            file=file,
            content_type=content_type,
            bytes=len(data),
            width=width,
            height=height,
            created_by=ctx.user.id,
        )
        ctx.db.add(receipt)
        ctx.db.flush()
        record(ctx, "receipt", receipt.id, "create", {kind: entry.id, "bytes": len(data)})
        receipt_id = idempotency.commit(ctx, key, "receipt", receipt.id)
    except BaseException:
        ctx.db.rollback()
        receipt_store.remove(ctx.group.id, file)
        raise
    if receipt_id != receipt.id:
        # The same key arrived twice at the same time and the other request won
        receipt_store.remove(ctx.group.id, file)
        return get_receipt(ctx, receipt_id), True
    return receipt, False


def delete(ctx: GroupContext, receipt_id: int) -> None:
    require_enabled()
    receipt = get_receipt(ctx, receipt_id)
    entry = ctx.db.get(FuelEntry, receipt.fuel_id) if receipt.fuel_id else ctx.db.get(Expense, receipt.expense_id)
    entry_service.not_settled(entry)
    owner = {"fuel": receipt.fuel_id} if receipt.fuel_id else {"expense": receipt.expense_id}
    record(ctx, "receipt", receipt.id, "delete", {**owner, "bytes": receipt.bytes})
    receipt_store.remove_after_commit(ctx.db, [(receipt.group_id, receipt.file)])
    ctx.db.delete(receipt)
    ctx.db.commit()


def file_of(ctx: GroupContext, receipt_id: int) -> tuple[Receipt, Path]:
    require_enabled()
    receipt = get_receipt(ctx, receipt_id)
    path = receipt_store.path_of(receipt.group_id, receipt.file)
    if not path.is_file():
        raise AppError(status.HTTP_404_NOT_FOUND, "receipt_not_found", "Receipt not found")
    return receipt, path


# ---------- Download of all photos ----------


class _Sink(io.RawIOBase):
    """A write-only stream collecting what zipfile writes, handed out chunk by chunk."""

    def __init__(self) -> None:
        self._chunks: list[bytes] = []

    def writable(self) -> bool:
        return True

    def write(self, data) -> int:
        self._chunks.append(bytes(data))
        return len(data)

    def take(self) -> bytes:
        data = b"".join(self._chunks)
        self._chunks.clear()
        return data


def zip_entries(ctx: GroupContext) -> list[tuple[str, Path]]:
    """(name in the archive, file) for every photo of the group, oldest entry first.

    Names tell date, kind and entry: 2026-11-24_fuel_12_1.jpg, 2026-11-20_repair_15_1.jpg.
    """
    require_enabled()
    rows = ctx.db.execute(
        select(Receipt, FuelEntry.date, Expense.date, Expense.category)
        .outerjoin(FuelEntry, FuelEntry.id == Receipt.fuel_id)
        .outerjoin(Expense, Expense.id == Receipt.expense_id)
        .where(Receipt.group_id == ctx.group.id)
        .order_by(Receipt.id)
    ).all()
    files: list[tuple[tuple, str, Path]] = []
    count: dict[tuple[str, int], int] = {}
    for receipt, fuel_date, expense_date, category in rows:
        if receipt.fuel_id:
            day, label, entry_id = fuel_date, "fuel", receipt.fuel_id
        else:
            day, label, entry_id = expense_date, category, receipt.expense_id
        number = count[(label, entry_id)] = count.get((label, entry_id), 0) + 1
        extension = RECEIPT_TYPES.get(receipt.content_type, "bin")
        name = f"{day.isoformat()}_{label}_{entry_id}_{number}.{extension}"
        files.append(((day, receipt.id), name, receipt_store.path_of(receipt.group_id, receipt.file)))
    files.sort(key=lambda item: item[0])
    return [(name, path) for _, name, path in files]


def zip_stream(files: list[tuple[str, Path]]) -> Iterator[bytes]:
    """A ZIP of the files, written while it is sent (photos are not compressed further)."""
    sink = _Sink()
    with zipfile.ZipFile(sink, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, path in files:
            try:
                source = path.open("rb")
            except OSError:
                continue  # removed in the meantime
            with source, archive.open(name, "w", force_zip64=True) as target:
                while chunk := source.read(256 * 1024):
                    target.write(chunk)
                    yield sink.take()
            yield sink.take()
    yield sink.take()
