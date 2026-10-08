"""Ingress body limits (R2-S8, design §7.12b BODY_LIMITS): refuse an oversized request BEFORE
any handler, dependency or auth check runs.

The cap is the first ROUTE_CAPS entry matching (method, path), else the default. A
Content-Length over the cap is refused without reading a byte. Otherwise the body is read
here, counting real bytes per chunk (a chunked body, or a Content-Length that lies), and only
a body within the cap is replayed to the app — so on a 413 the app is never called at all.
The body stays in memory: at most the route's cap, and nothing is spooled to disk."""
import re

from starlette.types import ASGIApp, Message, Receive, Scope, Send

MB = 1024 * 1024
# Ordered: the first match wins, so the narrower pattern comes first (§7.12b).
ROUTE_CAPS: list[tuple[str, re.Pattern, int]] = [
    ("POST", re.compile(r"^/api/v1/projects/[^/]+/bulk/process-flow/validate$"), 2 * MB),   # §7.12a
    ("POST", re.compile(r"^/api/v1/projects/[^/]+/bulk/[^/]+/validate$"), 10 * MB),          # §7.12
]


def cap_for(method: str, path: str, default_cap: int) -> int:
    for m, pattern, cap in ROUTE_CAPS:
        if m == method and pattern.match(path):
            return cap
    return default_cap


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, default_cap: int) -> None:
        self.app, self.default_cap = app, default_cap

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        cap = cap_for(scope["method"], scope["path"], self.default_cap)
        headers = dict(scope.get("headers") or [])
        length = headers.get(b"content-length")
        if length is not None and length.isdigit() and int(length) > cap:
            return await _too_large(send)

        chunks, seen = [], 0
        while True:
            message = await receive()
            if message["type"] != "http.request":          # the client went away mid-body
                return
            body = message.get("body", b"")
            seen += len(body)
            if seen > cap:
                return await _too_large(send)
            chunks.append(body)
            if not message.get("more_body", False):
                break
        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()                        # disconnect, after the body

        await self.app(scope, replay, send)


async def _too_large(send: Send) -> None:
    body = b'{"detail":"The request is too large."}'
    await send({"type": "http.response.start", "status": 413,
                "headers": [(b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})
