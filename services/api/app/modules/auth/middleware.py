"""ASGI middleware that restores trusted workforce request state from sessions."""

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.http_errors import session_unavailable_response
from app.core.session import SESSION_COOKIE_NAME, SessionUnavailableError, get_session_store
from app.modules.auth.dependencies import restore_request_session_context


class WorkforceSessionContextMiddleware:
    """Restore opaque server-session state before protected dependencies execute."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        if request.cookies.get(SESSION_COOKIE_NAME):
            try:
                await restore_request_session_context(request, get_session_store(request))
            except SessionUnavailableError:
                response = session_unavailable_response()
                await response(scope, receive, send)
                return

        await self._app(scope, receive, send)
