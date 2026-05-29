# -*- coding: utf-8 -*-
"""Tauri sidecar entry point for starting the Python backend."""
from __future__ import annotations

from collections.abc import Sequence
import json
import logging
import multiprocessing as mp
import os
import socket
import sys

import click

from qwenpaw.tauri.env import (
    DESKTOP_APP_ENV,
    DESKTOP_CORS_ORIGINS_ENV,
    DESKTOP_READY_PREFIX,
    ensure_desktop_cors_origins,
)
from qwenpaw.tauri.sidecar_logging import install_sidecar_logging

logger = logging.getLogger(__name__)


def _ensure_qwenpaw_app_not_loaded() -> None:
    if "qwenpaw.app._app" in sys.modules:
        raise RuntimeError(
            "qwenpaw app imported before desktop CORS origins were set",
        )


def _sync_loaded_qwenpaw_constant_cors_origins() -> None:
    constant_module = sys.modules.get("qwenpaw.constant")
    if constant_module is not None:
        constant_module.CORS_ORIGINS = os.environ.get(
            DESKTOP_CORS_ORIGINS_ENV,
            "",
        ).strip()


def _ensure_utf8_stdio() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _install_certifi_env() -> None:
    if os.environ.get("SSL_CERT_FILE"):
        return
    try:
        import certifi
    except Exception:
        logger.debug(
            "certifi is unavailable; leaving SSL bundle env unset",
            exc_info=True,
        )
        return

    cert_file = certifi.where()
    if not cert_file or not os.path.isfile(cert_file):
        logger.debug(
            "certifi returned an invalid certificate path: %r",
            cert_file,
        )
        return
    os.environ.setdefault("SSL_CERT_FILE", cert_file)
    os.environ.setdefault("REQUESTS_CA_BUNDLE", cert_file)
    os.environ.setdefault("CURL_CA_BUNDLE", cert_file)


def _ensure_cli_on_path() -> None:
    """Ensure the packaged ``qwenpaw`` CLI is reachable by child processes.

    In conda-pack / PyInstaller desktop builds the ``Scripts/`` directory
    containing ``qwenpaw.exe`` is not on the system PATH.  Skills like
    *cron* invoke ``qwenpaw cron ...`` as a shell command, which fails
    with "command not found" unless we prepend that directory here.

    This is a no-op when ``qwenpaw`` is already discoverable on PATH
    (e.g. pip-installed environments or development setups).
    """
    import shutil

    if shutil.which("qwenpaw"):
        return

    # Locate Scripts/ (Windows) or bin/ (Unix) relative to sys.executable
    scripts_dir = os.path.join(os.path.dirname(sys.executable), "Scripts")
    if not os.path.isdir(scripts_dir):
        scripts_dir = os.path.join(os.path.dirname(sys.executable), "bin")
    if not os.path.isdir(scripts_dir):
        # Fall back to the directory containing the interpreter itself
        scripts_dir = os.path.dirname(sys.executable)

    qwenpaw_exe = os.path.join(scripts_dir, "qwenpaw.exe")
    qwenpaw_bin = os.path.join(scripts_dir, "qwenpaw")
    if os.path.isfile(qwenpaw_exe) or os.path.isfile(qwenpaw_bin):
        os.environ["PATH"] = (
            scripts_dir + os.pathsep + os.environ.get("PATH", "")
        )
        logger.info(
            "Desktop: prepended %s to PATH for CLI access",
            scripts_dir,
        )


def _install_desktop_runtime() -> None:
    os.environ.setdefault(DESKTOP_APP_ENV, "1")
    # Ensure qwenpaw CLI is reachable for skills that shell out (e.g. cron)
    _ensure_cli_on_path()
    # Must run before importing the FastAPI app: it applies CORS middleware
    # from qwenpaw.constant.CORS_ORIGINS at import time.
    _ensure_qwenpaw_app_not_loaded()
    ensure_desktop_cors_origins()
    _sync_loaded_qwenpaw_constant_cors_origins()


def _run_click_command(
    command: click.Command,
    args: Sequence[str],
    label: str,
) -> None:
    try:
        command.main(args=args, standalone_mode=False)
    except click.ClickException as exc:
        message = f"desktop {label} failed: {exc.format_message()}"
        print(message, file=sys.stderr)
        raise RuntimeError(message) from exc
    except click.Abort as exc:
        message = f"desktop {label} aborted"
        print(message, file=sys.stderr)
        raise RuntimeError(message) from exc
    except SystemExit as exc:
        if exc.code in (None, 0):
            return
        message = f"desktop {label} exited with code {exc.code}"
        print(message, file=sys.stderr)
        raise RuntimeError(message) from exc


def _emit_backend_ready(port: int) -> None:
    payload = json.dumps({"port": port}, separators=(",", ":"))
    print(f"{DESKTOP_READY_PREFIX} {payload}", flush=True)


def _run_backend_server(log_level: str) -> None:
    import uvicorn

    from qwenpaw.config.utils import write_last_api
    from qwenpaw.constant import LOG_LEVEL_ENV
    from qwenpaw.utils.logging import (
        SuppressPathAccessLogFilter,
        setup_logger,
    )

    host = "127.0.0.1"
    normalized_log_level = log_level.lower()
    if normalized_log_level not in {
        "critical",
        "error",
        "warning",
        "info",
        "debug",
        "trace",
    }:
        normalized_log_level = "info"

    os.environ[LOG_LEVEL_ENV] = normalized_log_level
    os.environ.pop("QWENPAW_RELOAD_MODE", None)
    setup_logger(normalized_log_level)
    if normalized_log_level in ("debug", "trace"):
        from qwenpaw.cli.main import log_init_timings

        log_init_timings()

    logging.getLogger("uvicorn.access").addFilter(
        SuppressPathAccessLogFilter(["/console/push-messages"]),
    )

    config = uvicorn.Config(
        "qwenpaw.app._app:app",
        host=host,
        port=0,
        reload=False,
        workers=1,
        log_level=normalized_log_level,
    )
    backend_socket = config.bind_socket()
    try:
        port = _socket_port(backend_socket)
        write_last_api(host, port)
        _emit_backend_ready(port)
        uvicorn.Server(config).run(sockets=[backend_socket])
    except Exception:
        backend_socket.close()
        raise


def _socket_port(sock: socket.socket) -> int:
    address = sock.getsockname()
    if not isinstance(address, tuple) or len(address) < 2:
        raise RuntimeError(f"unexpected backend socket address: {address!r}")
    return int(address[1])


def main() -> None:
    _ensure_utf8_stdio()
    _install_desktop_runtime()

    from qwenpaw.constant import LOG_LEVEL_ENV, WORKING_DIR

    install_sidecar_logging(WORKING_DIR / "desktop.log")
    _install_certifi_env()

    # Auto-initialize if no config exists
    config_path = WORKING_DIR / "config.json"
    if not config_path.exists():
        from qwenpaw.cli.init_cmd import init_cmd

        _run_click_command(
            init_cmd,
            args=["--defaults", "--accept-security"],
            label="initialization",
        )

    _run_backend_server(os.environ.get(LOG_LEVEL_ENV, "info"))


if __name__ == "__main__":
    mp.freeze_support()
    main()
