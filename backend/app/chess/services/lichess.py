from __future__ import annotations

from functools import lru_cache
from typing import Any

import berserk
from fastapi import HTTPException

from app.core.config import settings


@lru_cache(maxsize=1)
def get_client() -> berserk.Client:
    token = settings.LICHESS_TOKEN
    if not token:
        raise HTTPException(
            status_code=503,
            detail={"error": "LICHESS_TOKEN is not configured."},
        )
    session = berserk.TokenSession(token)
    return berserk.Client(session=session)


def to_http_exception(exc: Exception) -> HTTPException:
    if isinstance(exc, berserk.exceptions.ResponseError):
        detail: dict[str, Any]
        if isinstance(exc.cause, dict):
            detail = exc.cause
        else:
            detail = {"error": str(exc)}
        return HTTPException(status_code=exc.status_code, detail=detail)
    return HTTPException(status_code=500, detail={"error": str(exc)})
