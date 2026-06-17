from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from starlette.responses import JSONResponse, Response

from app.services.auth_access_policy import AuthAccessDecision, auth_request_access


LoadSessionContext = Callable[[str | None], Awaitable[dict[str, Any] | None]]
AuthorizeRequest = Callable[[str, str, dict[str, Any] | None], AuthAccessDecision]
CallNext = Callable[[Any], Awaitable[Response]]


def build_auth_request_middleware(
    *,
    session_cookie_name: str,
    load_session_context: LoadSessionContext,
    authorize_request: AuthorizeRequest = auth_request_access,
) -> Callable[[Any, CallNext], Awaitable[Response]]:
    async def auth_request_middleware(request: Any, call_next: CallNext) -> Response:
        path = request.url.path
        initial_decision = authorize_request(request.method, path, None)
        if initial_decision.allowed and not initial_decision.requires_session_context:
            return await call_next(request)

        session_id = request.cookies.get(session_cookie_name)
        session_ctx = await load_session_context(session_id)
        decision = authorize_request(request.method, path, session_ctx)
        if not decision.allowed:
            resp = JSONResponse({"detail": decision.detail}, status_code=decision.status_code or 403)
            if decision.clear_session_cookie:
                resp.delete_cookie(session_cookie_name)
            return resp

        if session_ctx is not None:
            request.state.current_user = session_ctx
        return await call_next(request)

    return auth_request_middleware
