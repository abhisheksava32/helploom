"""One error shape for every API failure.

Every error response body is {"error": {"code", "message", "details"}} so the
frontend and the widget can handle failures with a single code path.
"""

from __future__ import annotations

import logging
from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


class PlanLimitExceeded(exceptions.APIException):
    """Raised by billing services when an organisation is over a plan limit.

    Usable outside DRF views too: websocket consumers catch it and send an error frame
    with the same code and message.
    """

    status_code = status.HTTP_402_PAYMENT_REQUIRED
    default_code = "plan_limit_exceeded"
    default_detail = "Your plan limit has been reached."

    def __init__(self, message: str, *, limit: str, used: int, allowed: int, plan: str) -> None:
        super().__init__(detail=message, code=self.default_code)
        self.details = {"limit": limit, "used": used, "allowed": allowed, "plan": plan}


class Conflict(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "conflict"
    default_detail = "The request conflicts with the current state of the resource."


class FileTooLarge(exceptions.APIException):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_code = "file_too_large"
    default_detail = "The uploaded file is too large."


class UnsupportedFileType(exceptions.APIException):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    default_code = "unsupported_file_type"
    default_detail = "This file type is not supported."


class ServiceUnavailable(exceptions.APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_code = "service_unavailable"
    default_detail = "A dependency is unavailable. Try again shortly."


def error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def _first_code(codes: Any) -> str | None:
    if isinstance(codes, str):
        return codes
    if isinstance(codes, list) and codes:
        return _first_code(codes[0])
    if isinstance(codes, dict) and codes:
        return _first_code(next(iter(codes.values())))
    return None


def _message_from_detail(detail: Any) -> str:
    if isinstance(detail, list) and detail:
        return _message_from_detail(detail[0])
    if isinstance(detail, dict) and detail:
        return _message_from_detail(next(iter(detail.values())))
    return str(detail)


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response:
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    response = drf_exception_handler(exc, context)
    if response is None:
        view = context.get("view")
        logger.exception("Unhandled API error in %s", type(view).__name__ if view else "unknown view")
        return Response(
            error_body("server_error", "Something went wrong on our side. Please try again."),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if isinstance(exc, exceptions.ValidationError):
        field_errors = exc.detail if isinstance(exc.detail, dict) else {"non_field_errors": exc.detail}
        body = error_body("validation_error", _message_from_detail(exc.detail), field_errors)
    elif isinstance(exc, exceptions.APIException):
        code = _first_code(exc.get_codes()) or exc.default_code
        details: dict[str, Any] = dict(getattr(exc, "details", {}) or {})
        wait = getattr(exc, "wait", None)
        if isinstance(exc, exceptions.Throttled) and wait is not None:
            # DRF already rounds wait up to whole seconds and sets Retry-After.
            details["retry_after"] = int(wait)
        body = error_body(str(code), _message_from_detail(exc.detail), details)
    else:  # pragma: no cover - DRF only returns responses for APIException
        body = error_body("error", str(exc))

    response.data = body
    return response
