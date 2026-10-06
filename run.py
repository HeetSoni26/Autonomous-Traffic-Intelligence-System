"""
run.py
Single-command entry point: starts the FastAPI server, and with DEMO_MODE=1
also boots the ZMQ broker, every agent, and the traffic simulator in-process.

    python run.py               # API only (agents/vision run as separate processes)
    DEMO_MODE=1 python run.py   # full self-contained demo, no cameras needed

Sets the Windows selector event-loop policy BEFORE uvicorn creates its loop,
which is required for pyzmq's async sockets to work on Windows.
"""
import os
import sys


def _patch_windows_loop() -> None:
    if sys.platform == "win32":
        import asyncio
        # Must happen before the event loop is created, or pyzmq async
        # sockets fail with "Proactor event loop does not implement add_reader".
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def main() -> None:
    _patch_windows_loop()

    import uvicorn
    from config.settings import settings

    host = os.environ.get("HOST", settings.API_HOST)
    port = int(os.environ.get("PORT", settings.API_PORT))

    uvicorn.run(
        "api.main:app",
        host=host,
        port=port,
        log_level=settings.LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    main()
