"""Ingress body limits (R2-S8): refuse an oversized request BEFORE any handler reads it.
Checks Content-Length up front and counts streamed bytes for chunked bodies."""
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Upload routes get a larger cap as they are built (xlsx 10 MB, flow JSON 2 MB, §7.12/§7.12a).
ROUTE_CAPS: dict[str, int] = {}


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, default_cap: int) -> None:
        self.app, self.default_cap = app, default_cap

    def _cap(self, path: str) -> int:
        for suffix, cap in ROUTE_CAPS.items():
            if path.endswith(suffix):
                return cap
        return self.default_cap

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        cap = self._cap(scope["path"])
        headers = dict(scope.get("headers") or [])
        length = headers.get(b"content-length")
        if length is not None and length.isdigit() and int(length) > cap:
            return await _too_large(send)
        seen = 0

        async def limited_receive() -> Message:
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > cap:
                    raise _TooLarge()
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _TooLarge:
            await _too_large(send)


class _TooLarge(Exception):
    pass


async def _too_large(send: Send) -> None:
    body = b'{"detail":"The request is too large."}'
    await send({"type": "http.response.start", "status": 413,
                "headers": [(b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})
