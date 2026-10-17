from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from .config import settings


class BodyLimitMiddleware:
    """Bound actual streamed bytes before multipart files can fill temporary disk."""

    def __init__(self, app, default_limit=1024**2):
        self.app = app
        self.default_limit = default_limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") not in {"POST", "PUT", "PATCH"}:
            return await self.app(scope, receive, send)
        limit = (
            settings().max_upload + 64 * 1024
            if scope.get("path", "").endswith("/artifacts")
            else self.default_limit
        )
        headers = dict(scope.get("headers", []))
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            declared = -1
        if declared < 0 or declared > limit:
            return await JSONResponse(
                {"detail": "Request body exceeds the intake limit"}, status_code=413
            )(scope, receive, send)
        total = 0

        async def bounded_receive():
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > limit:
                    raise HTTPException(413, "Streamed request exceeds the intake limit")
            return message

        await self.app(scope, bounded_receive, send)
