from __future__ import annotations

import signal
import threading

from marina.application.runtime import build_service
from marina.config.settings import Settings
from marina.interfaces.ipc import LocalRPCServer, default_socket_path


def main() -> None:
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
