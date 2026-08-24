"""Entry point for uvicorn."""

import os
import socket

import uvicorn

from backend.config import get_settings


def _port_in_use(port: int) -> bool:
    for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.2)
                if sock.connect_ex((host, port)) == 0:
                    return True
        except OSError:
            continue
    return False


if __name__ == "__main__":
    settings = get_settings()
    port = int(os.environ.get("PORT", "8080"))
    if "PORT" not in os.environ and _port_in_use(port):
        port = 8081
        print(f"Port 8080 is in use; serving the local demo on http://127.0.0.1:{port}")
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=port,
        reload=settings.environment == "local",
    )
