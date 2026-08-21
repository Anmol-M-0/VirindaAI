from __future__ import annotations

import os
import signal
import threading
from pathlib import Path

from virinda.application.runtime import build_service
from virinda.config.settings import Settings
from virinda.interfaces.ipc import LocalRPCServer, default_socket_path


def _bootstrap_environment() -> None:
    """Bootstrap environment variables and CA certificate paths prior to socket initialization."""
    # 1. Load .env files if present
    candidate_envs = (
        Path.cwd() / ".env",
        Path("/home/anmol/dev/active_projects/github/.env"),
        Path.home() / ".config" / "virinda" / ".env",
        Path.home() / ".config" / "chatgpt-cli" / ".env",
    )
    for p in candidate_envs:
        if p.exists() and p.is_file():
            try:
                import dotenv

                dotenv.load_dotenv(p)
            except Exception:
                pass

    # 2. Configure CA cert bundle paths for requests / urllib
    try:
        import certifi

        ca_bundle = certifi.where()
        if not os.environ.get("SSL_CERT_FILE"):
            os.environ["SSL_CERT_FILE"] = ca_bundle
        if not os.environ.get("REQUESTS_CA_BUNDLE"):
            os.environ["REQUESTS_CA_BUNDLE"] = ca_bundle
    except Exception:
        pass


def main() -> None:
    _bootstrap_environment()
    settings = Settings.from_env()
    service = build_service(settings)
    server = LocalRPCServer(service, default_socket_path(settings.data_dir))
    stop = threading.Event()

    def handle_stop(*_args) -> None:
        if stop.is_set():
            return
        stop.set()
        service.cancel("shutdown")
        # socketserver.shutdown() must run outside the serve_forever thread.
        threading.Thread(target=server.shutdown, name="marina-ipc-shutdown", daemon=True).start()

    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)

    try:
        server.start()
        print(f"marinad listening on {server.socket_path}")
        server.serve_forever()
    finally:
        server.shutdown()
        service.close()


if __name__ == "__main__":
    main()
