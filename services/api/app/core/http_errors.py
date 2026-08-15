"""HTTP mapping for stable Serviq API error envelopes."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.errors import AuthenticationError


def register_core_error_handlers(app: FastAPI) -> None:
    """Register baseline auth and request-validation envelope handlers."""

    @app.exception_handler(AuthenticationError)
    async def authentication_error_handler(
        _request: Request,
        _error: AuthenticationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "code": "UNAUTHENTICATED",
                    "message": "Authentication required.",
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        fields: dict[str, str] = {}
        for item in error.errors():
            location = [str(part) for part in item.get("loc", ()) if part != "body"]
            field = ".".join(location) or "request"
            fields.setdefault(field, str(item.get("msg", "Invalid value")))
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed.",
                    "fields": fields,
                }
            },
        )
