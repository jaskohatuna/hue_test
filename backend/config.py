"""Read and atomically save connection settings in the backend's .env file."""

import os
from ipaddress import ip_address
from pathlib import Path
from tempfile import mkstemp

from dotenv import dotenv_values, set_key

# HUE_ENV_FILE lets a second instance (e.g. with dev/mock_bridge.py) keep its own settings.
ENV_PATH = Path(os.environ.get("HUE_ENV_FILE") or Path(__file__).parent / ".env").resolve()

# Origins of the mobile app's WebView and of the Vite dev server in Chrome.
APP_ORIGINS = (
    "capacitor://localhost",  # iOS
    "http://localhost",  # Android (androidScheme: http)
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def read_config() -> tuple[str, str]:
    values = dotenv_values(ENV_PATH)
    return (
        (values.get("HUE_BRIDGE_IP") or "").strip(),
        (values.get("HUE_APP_KEY") or "").strip(),
    )


def bridge_host(value: str) -> str:
    """Accept an IP address, without a URL scheme or port."""
    address = ip_address(value)
    return f"[{address}]" if address.version == 6 else str(address)


def write_config(ip: str, key: str) -> None:
    """Keep comments/other settings; replace .env only after both values are saved."""
    contents = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else ""
    descriptor, filename = mkstemp(prefix=".env-", suffix=".tmp", dir=ENV_PATH.parent)
    temporary = Path(filename)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(contents)
        set_key(temporary, "HUE_BRIDGE_IP", ip)
        set_key(temporary, "HUE_APP_KEY", key)
        temporary.replace(ENV_PATH)
    finally:
        temporary.unlink(missing_ok=True)
