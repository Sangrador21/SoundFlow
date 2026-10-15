from __future__ import annotations

from urllib.parse import urlsplit


def normalize_url(value: str) -> str:
    parts = urlsplit(value.rstrip("/"))
    if (parts.scheme not in {"http", "https"} or not parts.hostname
            or parts.username or parts.password or parts.query or parts.fragment
            or parts.path not in {"", "/"}):
        raise ValueError("Usa una URL base, por ejemplo http://127.0.0.1:5000")
    _ = parts.port  # Valida puerto
    return value.rstrip("/")
