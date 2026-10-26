"""One error shape for every API failure.

Every error response body is {"error": {"code", "message", "details"}} so the
frontend and the widget can handle failures with a single code path. Websocket
consumers send the same triple as an error frame (see error_frame).
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


class HelploomError(exceptions.APIException):
    """An API error with a stable code, a friendly message and structured details.

    The constructor mirrors APIException(detail, code) and adds details, so
    Conflict("Already invited.", code="already_invited") reads naturally.
    """

    def __init__(self, detail: Any = None, code: str | None = None, *, details: dict[str, Any] | None = None):
        super().__init__(detail=detail, code=code)
        self.details: dict[str, Any] = dict(details or {})


class PlanLimitExceeded(HelploomError):
    """Raised by billing services when an organisation is over a plan limit.

    Usable outside DRF views too: websocket consumers catch it and send an error frame
    with the same code and message.
    """

    status_code = status.HTTP_402_PAYMENT_REQUIRED
    default_code = "plan_limit_exceeded"
    default_detail = "Your plan limit has been reached."

    def __init__(self, message: str, *, limit: str, used: int, allowed: int, plan: str) -> None:
        super().__init__(
            message,
            self.default_code,
            details={"limit": limit, "used": used, "allowed": allowed, "plan": plan},
        )


class Conflict(HelploomError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "conflict"
    default_detail = "The request conflicts with the current state of the resource."


class InvalidCredentials(exceptions.AuthenticationFailed):
    """Wrong email or password. One message for both, so login cannot probe for accounts."""

    default_code = "invalid_credentials"
    default_detail = "The email or password is incorrect."


class FileTooLarge(HelploomError):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_code = "file_too_large"
    default_detail = "The uploaded file is too large."


class UnsupportedFileType(HelploomError):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    default_code = "unsupported_file_type"
    default_detail = "This file type is not supported."


class ServiceUnavailable(HelploomError):
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
        # simplejwt puts the real code under "code" next to "detail" and "messages".
        if isinstance(codes.get("code"), str):
            return str(codes["code"])
        return _first_code(next(iter(codes.values())))
    return None


def _message_from_detail(detail: Any) -> str:
    if isinstance(detail, list) and detail:
        return _message_from_detail(detail[0])
    if isinstance(detail, dict) and detail:
        if "detail" in detail:
            return _message_from_detail(detail["detail"])
        return _message_from_detail(next(iter(detail.values())))
    return str(detail)


def describe_exception(exc: exceptions.APIException) -> tuple[str, str, dict[str, Any]]:
    """(code, message, details) for an API exception, shared by REST and websockets."""
    if isinstance(exc, exceptions.ValidationError):
        field_errors = exc.detail if isinstance(exc.detail, dict) else {"non_field_errors": exc.detail}
        return "validation_error", _message_from_detail(exc.detail), dict(field_errors)

    code = _first_code(exc.get_codes()) or str(exc.default_code)
    details: dict[str, Any] = dict(getattr(exc, "details", {}) or {})
    wait = getattr(exc, "wait", None)
    if isinstance(exc, exceptions.Throttled) and wait is not None:
        # DRF already rounds wait up to whole seconds and sets Retry-After.
        details["retry_after"] = int(wait)
    return code, _message_from_detail(exc.detail), details


def error_frame(exc: exceptions.APIException, **extra: Any) -> dict[str, Any]:
    """The websocket error frame for an exception a service raised."""
    code, message, details = describe_exception(exc)
    return {"type": "error", "code": code, "message": message, "details": details, **extra}


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response:
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    response = drf_exception_handler(exc, context)
    if response is None or not isinstance(exc, exceptions.APIException):
        view = context.get("view")
        logger.exception("Unhandled API error in %s", type(view).__name__ if view else "unknown view")
        return Response(
            error_body("server_error", "Something went wrong on our side. Please try again."),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    code, message, details = describe_exception(exc)
    response.data = error_body(code, message, details)
    return response
