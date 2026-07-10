from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.schemas import SENSITIVE_IDENTITY_FIELDS


def _mask_input(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: ("***" if key in SENSITIVE_IDENTITY_FIELDS else val)
            for key, val in value.items()
        }
    return value


async def sanitized_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Strip encrypted identity values from any validation error body.

    Applied globally — document_number/pin_egn must never round-trip into a
    client-visible error anywhere. Field-level errors drop ``input`` entirely;
    cross-field (model-level) errors carry the whole payload dict as ``input``,
    so we mask the sensitive keys wherever they appear.
    """
    sanitized: list[dict[str, Any]] = []
    for raw in exc.errors():
        error = dict(raw)
        loc = error.get("loc", ())
        if any(str(part) in SENSITIVE_IDENTITY_FIELDS for part in loc):
            error.pop("input", None)
        elif "input" in error:
            error["input"] = _mask_input(error["input"])
        sanitized.append(error)
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(sanitized)})
