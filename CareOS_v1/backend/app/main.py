import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .api import router
from .config import get_settings
from .db import init_db

settings = get_settings()
_auth_rate_limit_state: dict[str, list[float]] = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="CareOS Clinical API",
    version="0.1.0",
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid4()))
    started = time.perf_counter()
    if settings.is_production and request.method == "POST" and request.url.path.startswith(f"{settings.api_prefix}/auth/"):
        now = time.monotonic()
        client_key = request.client.host if request.client else "unknown"
        recent = [timestamp for timestamp in _auth_rate_limit_state.get(client_key, []) if now - timestamp < settings.auth_rate_limit_window_seconds]
        if len(recent) >= settings.auth_rate_limit_requests:
            return JSONResponse(status_code=429, content={"detail": "Too many authentication attempts"}, headers={"Retry-After": str(settings.auth_rate_limit_window_seconds)})
        recent.append(now)
        _auth_rate_limit_state[client_key] = recent
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith(settings.api_prefix) else response.headers.get("Cache-Control", "")
    response.headers["Server-Timing"] = f"app;dur={(time.perf_counter() - started) * 1000:.2f}"
    return response


@app.exception_handler(Exception)
async def unhandled_exception(_: Request, __: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(router, prefix=settings.api_prefix)
