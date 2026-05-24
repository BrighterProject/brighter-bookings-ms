from __future__ import annotations

import logging
import sys

from loguru import logger
from opentelemetry.trace import (
    INVALID_SPAN,
    INVALID_SPAN_CONTEXT,
    get_current_span,
)


class _InterceptHandler(logging.Handler):
    """Route stdlib logging (uvicorn, fastapi, tortoise) through loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno  # type: ignore[assignment]

        frame, depth = sys._getframe(6), 6
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back  # type: ignore[assignment]
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def _add_trace_context(record: dict) -> None:  # type: ignore[type-arg]
    """Inject active OTEL span IDs into every loguru record."""
    record["extra"].setdefault("otelTraceID", "0" * 32)
    record["extra"].setdefault("otelSpanID", "0" * 16)
    record["extra"].setdefault("otelTraceSampled", False)

    span = get_current_span()
    if span == INVALID_SPAN:
        return
    ctx = span.get_span_context()
    if ctx == INVALID_SPAN_CONTEXT:
        return

    record["extra"]["otelTraceID"] = format(ctx.trace_id, "032x")
    record["extra"]["otelSpanID"] = format(ctx.span_id, "016x")
    record["extra"]["otelTraceSampled"] = ctx.trace_flags.sampled


def setup_logging(level: str | None = None) -> None:
    """Configure loguru with trace-correlation and stdlib interception."""
    import os

    level = level or os.environ.get("LOG_LEVEL", "INFO")
    # Default False in containers so Promtail regex matches raw text without ANSI codes.
    # Set LOG_COLORIZE=true in docker-compose for local dev pretty-printing.
    colorize = os.environ.get("LOG_COLORIZE", "false").lower() == "true"

    logger.remove()
    logger.configure(patcher=_add_trace_context)  # type: ignore
    logger.add(
        sys.stdout,
        level=level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<dim>{extra[otelTraceID]}</dim> | "
            "<cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
        ),
        colorize=colorize,
    )

    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi", "tortoise"):
        log = logging.getLogger(name)
        log.handlers = [_InterceptHandler()]
        log.propagate = False
