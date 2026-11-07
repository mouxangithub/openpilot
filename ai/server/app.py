"""aiohttp Application assembly."""

from __future__ import annotations

from pathlib import Path

from aiohttp import web

from ai.core.config.schema import AIOPConfig, load_config
from ai.server.op_routes import setup_routes


async def make_app(config: AIOPConfig | None = None) -> web.Application:
    app = web.Application()
    app["config"] = config or load_config()
    setup_routes(app)
    return app


def main() -> None:
    import asyncio
    config = load_config()
    app = asyncio.run(make_app(config))
    web.run_app(app, host="127.0.0.1", port=8080)


if __name__ == "__main__":
    main()
