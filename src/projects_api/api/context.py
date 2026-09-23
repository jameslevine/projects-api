"""Request correlation: one id per request, shared by the response header, problem bodies and logs.

Precedence for the id:

1. API Gateway `requestContext.requestId` (the id in the gateway access log and, via
   `x-amzn-RequestId`, what the client already sees);
2. the Lambda `aws_request_id` (direct invocations without a gateway);
3. an incoming `X-Request-Id` header (local runs behind another proxy) if short and printable;
4. a fresh UUID4.

The id is resolved once per request and stashed on `request.state`, which is backed by the ASGI
scope, so every `Request` view of the same scope (middleware, route, exception handlers) agrees.
"""

import time
from uuid import uuid4

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from projects_api.observability import logger

REQUEST_ID_HEADER = "X-Request-Id"
_MAX_CLIENT_REQUEST_ID_LENGTH = 128


def request_id(request: Request) -> str:
    """Return the correlation id for this request, resolving and stashing it on first use."""
    existing = getattr(request.state, "request_id", None)
    if isinstance(existing, str):
        return existing
    resolved = _resolve(request.scope, request.headers.get(REQUEST_ID_HEADER))
    request.state.request_id = resolved
    return resolved


def _resolve(scope: Scope, header: str | None) -> str:
    event = scope.get("aws.event")
    if isinstance(event, dict):
        gateway_id = event.get("requestContext", {}).get("requestId")
        if gateway_id:
            return str(gateway_id)
    context = scope.get("aws.context")
    lambda_id = getattr(context, "aws_request_id", None) if context is not None else None
    if lambda_id:
        return str(lambda_id)
    if header:
        candidate = header.strip()
        if 0 < len(candidate) <= _MAX_CLIENT_REQUEST_ID_LENGTH and candidate.isprintable():
            return candidate
    return str(uuid4())


def _owner_id(scope: Scope) -> str | None:
    """The API key *id* from the gateway event; never the key value. None outside API Gateway."""
    event = scope.get("aws.event")
    if not isinstance(event, dict):
        return None
    key_id = event.get("requestContext", {}).get("identity", {}).get("apiKeyId")
    return str(key_id) if key_id else None


class RequestContextMiddleware:
    """Set `X-Request-Id` on every response and log one structured line per request.

    Pure ASGI rather than `BaseHTTPMiddleware`: it sees the real `http.response.start` message,
    adds no buffering, and can observe an unhandled exception (logged as 500 and re-raised so
    Starlette's server-error handler builds the problem response, which carries the same id via
    `problem()`). The log line never includes bodies, query strings or headers.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        rid = request_id(Request(scope))
        logger.set_correlation_id(rid)
        started = time.perf_counter()
        status = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message).setdefault(REQUEST_ID_HEADER, rid)
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            route = scope.get("route")
            logger.info(
                "request completed",
                route=getattr(route, "path_format", None) or scope["path"],
                method=scope["method"],
                status=status,
                owner_id=_owner_id(scope),
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
                request_id=rid,
            )
