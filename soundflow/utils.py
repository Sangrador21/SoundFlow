from __future__ import annotations


def format_seconds(value: float) -> str:
    """Convierte segundos a MM:SS."""
    value = max(0, int(value))
    minutes, seconds = divmod(value, 60)
    return f"{minutes:02d}:{seconds:02d}"
