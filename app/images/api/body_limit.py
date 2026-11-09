from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class _BodyTooLarge(HTTPException):
    """Raised from `receive`. An HTTPException so FastAPI's body parser re-raises it rather than turning it into
    a 400 "error parsing the body"; the app's exception handling then renders the 413."""

    def __init__(self, max_bytes: int) -> None:
        super().__init__(413, f"Request body exceeds the {max_bytes}-byte limit")


class MaxBodySizeMiddleware:
    """Rejects request bodies over `max_bytes` with 413, before the app parses (or spools) them.

    Pure ASGI rather than BaseHTTPMiddleware, so the body is never buffered here. Two checks:
      - a declared Content-Length over the limit is refused before reading a byte;
      - otherwise (chunked, or a client that lies) the bytes are counted as they arrive.

    In production a proxy or ingress usually enforces the same limit first; this keeps the app safe without one.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared: str | None = Headers(scope=scope).get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_bytes:
            await self._reject(scope, receive, send)
            return

        received: int = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _BodyTooLarge(self.max_bytes)
            return message

        response_started = False

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _BodyTooLarge:
            # Only reached if the app has no HTTPException handling of its own (plain ASGI apps).
            if response_started:
                raise
            await self._reject(scope, receive, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        detail = f"Request body exceeds the {self.max_bytes}-byte limit"
        await JSONResponse({"detail": detail}, status_code=413, headers={"Connection": "close"})(scope, receive, send)
