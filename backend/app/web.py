"""ASGI entry point: the API under /api plus the built frontend from FRONTEND_DIST.

Run with: uvicorn app.web:application
"""

import asyncio
import logging
import mimetypes
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from app import config
from app.db.database import SessionLocal
from app.main import app as api
from app.middleware.security_headers import add_security_headers
from app.services import inactive_accounts, notification_service, receipt_store, setup_service
from app.services.background import ThreadRuns

if not logging.getLogger().handlers:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(levelname)s:     %(name)s %(message)s",
    )
logger = logging.getLogger("app")

mimetypes.add_type("application/manifest+json", ".webmanifest")

# Files that must always be revalidated so updates (service worker!) reach clients
NO_CACHE_FILES = {"index.html", "sw.js", "push-sw.js", "registerSW.js", "manifest.webmanifest"}
LONG_CACHE = "public, max-age=31536000, immutable"
ICON_CACHE = "public, max-age=604800"


class SpaStaticFiles(StaticFiles):
    """Static frontend with client-side routing: unknown pages fall back to index.html."""

    async def get_response(self, path: str, scope: Scope):
        served = path
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or self._looks_like_file(path):
                raise
            served = "index.html"
            response = await super().get_response(served, scope)
        name = Path(served).name or "index.html"
        if path in ("", ".") or name in NO_CACHE_FILES:
            response.headers["Cache-Control"] = "no-cache"
        elif served.startswith("assets/"):
            response.headers["Cache-Control"] = LONG_CACHE
        else:
            response.headers["Cache-Control"] = ICON_CACHE
        return response

    @staticmethod
    def _looks_like_file(path: str) -> bool:
        # Missing assets stay 404 instead of returning HTML with status 200
        return path.startswith("assets/") or "." in Path(path).name


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        config.validate()
    except config.ConfigError as exc:
        logger.error("Configuration error: %s", exc)
        raise
    announce_setup_token()
    reminders = asyncio.create_task(remind()) if config.push_enabled() else None
    cleanup = asyncio.create_task(delete_inactive()) if config.get_inactive_delete_months() else None
    sweep = asyncio.create_task(sweep_receipts()) if config.receipts_enabled() else None
    try:
        yield
    finally:
        for task in (reminders, cleanup, sweep):
            if task is not None:
                task.cancel()
        # A round that is busy (e.g. deleting an account) finishes instead of stopping halfway
        await asyncio.gather(*(runs.wait() for runs in (REMINDER_RUNS, INACTIVE_RUNS, SWEEP_RUNS)))


# Reminders by Web Push: one round a minute, in a thread so requests never wait for it.
# Exactly one instance runs (SQLite), so there is no second loop to coordinate with.
REMINDER_INTERVAL_SECONDS = 60
REMINDER_RUNS = ThreadRuns("reminder")


async def remind() -> None:
    while True:
        await asyncio.sleep(REMINDER_INTERVAL_SECONDS)
        try:
            await REMINDER_RUNS.run(notification_service.run_scheduled)
        except OperationalError:
            logger.warning("Reminders skipped: database not ready")
        except Exception:
            logger.exception("Reminders failed")


# INACTIVE_DELETE_MONTHS: warn and delete unused accounts, once an hour (first round after
# a few minutes, so a restart loop never runs it in quick succession)
INACTIVE_FIRST_DELAY_SECONDS = 5 * 60
INACTIVE_INTERVAL_SECONDS = 60 * 60
INACTIVE_RUNS = ThreadRuns("inactive accounts")


async def delete_inactive() -> None:
    await asyncio.sleep(INACTIVE_FIRST_DELAY_SECONDS)
    while True:
        try:
            await INACTIVE_RUNS.run(lambda: inactive_accounts.run_scheduled(SessionLocal))
        except OperationalError:
            logger.warning("Inactive accounts skipped: database not ready")
        except Exception:
            logger.exception("Deleting inactive accounts failed")
        await asyncio.sleep(INACTIVE_INTERVAL_SECONDS)


# Receipt photos: remove files left without a database row (a crash between writing and
# committing, or a deletion interrupted after its commit), once an hour
RECEIPT_SWEEP_FIRST_DELAY_SECONDS = 10 * 60
RECEIPT_SWEEP_INTERVAL_SECONDS = 60 * 60
SWEEP_RUNS = ThreadRuns("receipt cleanup")


async def sweep_receipts() -> None:
    await asyncio.sleep(RECEIPT_SWEEP_FIRST_DELAY_SECONDS)
    while True:
        try:
            await SWEEP_RUNS.run(lambda: receipt_store.run_sweep(SessionLocal))
        except OperationalError:
            logger.warning("Receipt cleanup skipped: database not ready")
        except Exception:
            logger.exception("Receipt cleanup failed")
        await asyncio.sleep(RECEIPT_SWEEP_INTERVAL_SECONDS)


def announce_setup_token() -> None:
    db = SessionLocal()
    try:
        needed = setup_service.needs_setup(db)
    except OperationalError:
        logger.warning("Database not migrated yet; run 'alembic upgrade head'")
        return
    finally:
        db.close()
    if not needed:
        return
    token = setup_service.issue_token()
    banner = "=" * 72
    logger.warning(
        "\n%s\nNo account exists yet. Open %s/setup and enter this setup token:\n\n    %s\n\n"
        "The token is valid until the first account is created (a restart issues a new one).\n%s",
        banner,
        config.get_public_url(),
        token,
        banner,
    )


def create_application(frontend_dist: Path | None = None) -> FastAPI:
    application = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    application.middleware("http")(add_security_headers)
    application.mount("/api", api)
    if frontend_dist is not None and (frontend_dist / "index.html").is_file():
        application.mount("/", SpaStaticFiles(directory=frontend_dist, html=True), name="frontend")
    else:
        logger.info("No frontend build found; serving the API only")
    return application


def _default_dist() -> Path | None:
    value = os.getenv("FRONTEND_DIST", "").strip()
    return Path(value) if value else None


application = create_application(_default_dist())
