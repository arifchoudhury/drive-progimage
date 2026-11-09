"""Liveness and readiness probes, for container healthchecks and orchestrators. Unauthenticated by design.

A feature module of its own (not app/core) because readiness checks the images feature's storage, and core must not
depend on features.
"""

import logging
from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.images.api.dependencies import get_storage
from app.images.domain.ports import ImageStorage

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

CheckResult = Literal["ok", "error"]


class LivenessResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not ready"]
    checks: dict[str, CheckResult]


@router.get("/healthz")
def liveness() -> LivenessResponse:
    """The process is up and serving requests. No I/O, so a slow dependency never gets the container restarted."""
    return LivenessResponse()


@router.get(
    "/readyz",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse, "description": "A dependency failed"}},
)
def readiness(
    response: Response,
    session: Annotated[Session, Depends(get_session)],
    storage: Annotated[ImageStorage, Depends(get_storage)],
) -> ReadinessResponse:
    """Every dependency a request needs is reachable: the database answers and storage accepts writes."""
    checks = {
        "database": _run("database", lambda: session.execute(text("SELECT 1"))),
        "storage": _run("storage", storage.check),
    }
    ready = all(result == "ok" for result in checks.values())
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(status="ready" if ready else "not ready", checks=checks)


def _run(name: str, check: Callable[[], object]) -> CheckResult:
    try:
        check()
    except Exception:
        # Details go to the log, not the (unauthenticated) response.
        logger.exception("readiness check %r failed", name)
        return "error"
    return "ok"
