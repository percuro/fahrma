"""Receipt photos: attach (raw image as the body), show, delete, download all as a ZIP."""

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import FileResponse, StreamingResponse

from app.api.dependencies.group import require_member
from app.config import get_max_receipt_bytes
from app.errors import AppError
from app.schemas.receipts import ReceiptRead
from app.services import receipt_service
from app.services.access import GroupContext
from app.services.idempotency import idempotency_key

router = APIRouter()

# The image is served on its own: nothing in it may run, load or be framed
IMAGE_POLICY = "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox"


async def receipt_body(request: Request) -> bytes:
    """The raw body, at most MAX_RECEIPT_KB (checked while reading, not only by the header)."""
    maximum = get_max_receipt_bytes()
    too_large = AppError(
        status.HTTP_413_CONTENT_TOO_LARGE, "receipt_too_large", "The photo is too large", max_kb=maximum // 1024
    )
    length = request.headers.get("content-length", "")
    if length.isdigit() and int(length) > maximum:
        raise too_large
    size, chunks = 0, []
    async for chunk in request.stream():
        size += len(chunk)
        if size > maximum:
            raise too_large
        chunks.append(chunk)
    return b"".join(chunks)


def _content_type(request: Request) -> str:
    return request.headers.get("content-type", "").split(";", 1)[0].strip().lower()


def _created(receipt, replayed: bool, response: Response) -> ReceiptRead:
    if replayed:
        response.status_code = status.HTTP_200_OK
        response.headers["Idempotent-Replayed"] = "true"
    return ReceiptRead.model_validate(receipt, from_attributes=True)


@router.post("/fuel/{fuel_id}/receipts", response_model=ReceiptRead, status_code=status.HTTP_201_CREATED)
def add_fuel_receipt(
    fuel_id: int,
    request: Request,
    response: Response,
    ctx: GroupContext = Depends(require_member),
    data: bytes = Depends(receipt_body),
    key: str | None = Depends(idempotency_key),
):
    """Attach a photo (body: the JPEG or WebP image, Content-Type image/jpeg or image/webp)."""
    receipt, replayed = receipt_service.add(ctx, "fuel", fuel_id, data, _content_type(request), key)
    return _created(receipt, replayed, response)


@router.post("/expenses/{expense_id}/receipts", response_model=ReceiptRead, status_code=status.HTTP_201_CREATED)
def add_expense_receipt(
    expense_id: int,
    request: Request,
    response: Response,
    ctx: GroupContext = Depends(require_member),
    data: bytes = Depends(receipt_body),
    key: str | None = Depends(idempotency_key),
):
    """Attach a photo (body: the JPEG or WebP image, Content-Type image/jpeg or image/webp)."""
    receipt, replayed = receipt_service.add(ctx, "expense", expense_id, data, _content_type(request), key)
    return _created(receipt, replayed, response)


@router.get("/receipts.zip")
def download_receipts(ctx: GroupContext = Depends(require_member)):
    """All photos of the group in one ZIP, named by date, kind and entry."""
    files = receipt_service.zip_entries(ctx)
    filename = f"fahrma-receipts-{ctx.group.id}.zip"
    return StreamingResponse(
        receipt_service.zip_stream(files),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"},
    )


@router.get("/receipts/{receipt_id}")
def show_receipt(receipt_id: int, ctx: GroupContext = Depends(require_member)):
    receipt, path = receipt_service.file_of(ctx, receipt_id)
    extension = path.suffix
    return FileResponse(
        path,
        media_type=receipt.content_type,
        headers={
            "Content-Disposition": f'inline; filename="receipt-{receipt.id}{extension}"',
            "Content-Security-Policy": IMAGE_POLICY,
            "X-Content-Type-Options": "nosniff",
            # Revalidated each time (cheap, by ETag): an id can be used again after its photo was deleted
            "Cache-Control": "private, no-cache",
        },
    )


@router.delete("/receipts/{receipt_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_receipt(receipt_id: int, ctx: GroupContext = Depends(require_member)):
    receipt_service.delete(ctx, receipt_id)
