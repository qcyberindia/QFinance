"""
Structured error format — API Specification V1 §0.3, Architecture §12/API-005.
Every error response uses this single shape:
{ "error": { "code": "...", "message": "...", "fields": {...} } }
`fields` is omitted for non-validation errors.
WRITTEN, NOT EXECUTED.
"""
from fastapi import Request, status
from fastapi.responses import JSONResponse


class QFinanceAPIError(Exception):
    """Base application error. Route/service code raises this; the handler below
    is the ONLY place that formats the response body — no route hand-rolls error JSON
    (Architecture §12)."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        fields: dict[str, str] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.fields = fields
        super().__init__(message)


# Standard, reusable errors (API Spec §0.3 — generic 401/403/404/500 codes,
# not re-specified per endpoint).
class Unauthenticated(QFinanceAPIError):
    def __init__(self) -> None:
        super().__init__("UNAUTHENTICATED", "Authentication is required.", status.HTTP_401_UNAUTHORIZED)


class Forbidden(QFinanceAPIError):
    def __init__(self, message: str = "You do not have permission to perform this action.") -> None:
        super().__init__("FORBIDDEN", message, status.HTTP_403_FORBIDDEN)


class NotFound(QFinanceAPIError):
    def __init__(self, message: str = "The requested resource was not found.") -> None:
        super().__init__("NOT_FOUND", message, status.HTTP_404_NOT_FOUND)


class CsrfMismatch(QFinanceAPIError):
    def __init__(self) -> None:
        super().__init__("CSRF_MISMATCH", "CSRF token missing or invalid.", status.HTTP_403_FORBIDDEN)


async def qfinance_error_handler(request: Request, exc: QFinanceAPIError) -> JSONResponse:
    body: dict = {"error": {"code": exc.code, "message": exc.message}}
    if exc.fields:
        body["error"]["fields"] = exc.fields
    return JSONResponse(status_code=exc.status_code, content=body)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # STATE-003 — never leak raw exception text to the client.
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": {"code": "INTERNAL_ERROR", "message": "Something went wrong. Please try again."}},
    )
