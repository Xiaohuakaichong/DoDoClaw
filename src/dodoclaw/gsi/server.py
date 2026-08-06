from __future__ import annotations

import logging
import threading
from typing import Any, Callable

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from dodoclaw.gsi.state import GameStateStore

logger = logging.getLogger(__name__)

OnUpdate = Callable[[dict[str, Any]], None]


def create_gsi_app(
    store: GameStateStore,
    auth_token: str,
    on_update: OnUpdate | None = None,
) -> FastAPI:
    app = FastAPI(title="DoDoClaw GSI", docs_url=None, redoc_url=None)

    @app.get("/health")
    async def health() -> dict[str, Any]:
        snap = store.get()
        return {
            "ok": True,
            "updates": store.update_count,
            "clock": snap.clock_time,
            "hero": snap.hero_name,
            "game_state": snap.game_state,
        }

    @app.post("/")
    async def gsi_ingest(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> JSONResponse:
        # Dota sends JSON body; auth may be in body.auth.token or header depending on cfg
        try:
            payload = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"invalid json: {exc}") from exc

        body_token = None
        auth = payload.get("auth") if isinstance(payload, dict) else None
        if isinstance(auth, dict):
            body_token = auth.get("token")

        if auth_token:
            header_token = None
            if authorization and authorization.lower().startswith("bearer "):
                header_token = authorization[7:].strip()
            if body_token != auth_token and header_token != auth_token:
                # Still accept empty first probes carefully? Prefer strict.
                raise HTTPException(status_code=401, detail="invalid gsi token")

        store.update(payload)
        if on_update:
            try:
                on_update(payload)
            except Exception:
                logger.exception("on_update failed")

        return JSONResponse({"ok": True})

    return app


class GSIServer:
    """Run FastAPI GSI listener in a background thread."""

    def __init__(
        self,
        store: GameStateStore,
        host: str = "127.0.0.1",
        port: int = 3000,
        auth_token: str = "dodoclaw_secret",
        on_update: OnUpdate | None = None,
    ) -> None:
        self.store = store
        self.host = host
        self.port = port
        self.auth_token = auth_token
        self.on_update = on_update
        self._thread: threading.Thread | None = None
        self._server: uvicorn.Server | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        app = create_gsi_app(self.store, self.auth_token, self.on_update)
        config = uvicorn.Config(
            app,
            host=self.host,
            port=self.port,
            log_level="warning",
            access_log=False,
        )
        self._server = uvicorn.Server(config)

        def _run() -> None:
            assert self._server is not None
            self._server.run()

        self._thread = threading.Thread(target=_run, name="gsi-server", daemon=True)
        self._thread.start()
        logger.info("GSI server listening on http://%s:%s/", self.host, self.port)

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
