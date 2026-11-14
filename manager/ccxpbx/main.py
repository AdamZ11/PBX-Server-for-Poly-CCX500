"""ASGI application: provisioning server (/prov) + admin UI (/)."""
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import config, db, prov, web


def create_app() -> FastAPI:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.PROV_DIR.mkdir(parents=True, exist_ok=True)
    conn = db.connect()
    try:
        db.init_db(conn)
    finally:
        conn.close()

    app = FastAPI(title="ccxpbx", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(SessionMiddleware, secret_key=config.SECRET_KEY or db.gen_secret(48),
                       session_cookie="ccxpbx_session", same_site="strict", max_age=8 * 3600)

    @app.exception_handler(web.LoginRequired)
    async def _login_required(request: Request, exc):
        return RedirectResponse("/login", status_code=303)

    @app.middleware("http")
    async def _security_headers(request: Request, call_next):
        response = await call_next(request)
        if not request.url.path.startswith("/prov/"):
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "same-origin"
        return response

    app.include_router(prov.router)
    app.include_router(web.router)
    app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
    return app


app = create_app()
