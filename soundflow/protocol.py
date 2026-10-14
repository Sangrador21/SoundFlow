from __future__ import annotations

import json
import struct
from typing import Any

MAGIC = b"SFLW"
VERSION = 1
# 8 KB mantiene cada datagrama
CHUNK_SIZE = 8 * 1024
BUFFER_THRESHOLD = 128 * 1024
MAX_DATAGRAM = 9 * 1024

# MAGIC(4) VERSION(B) TYPE(B) SESSION(16) SEQ(I) TOTAL(I) PAYLOAD_LEN(H)
_HEADER = struct.Struct("!4sBB16sIIH")
TYPE_AUDIO_CHUNK = 1


def encode_json(message: dict[str, Any]) -> bytes:
    return json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def decode_json(data: bytes) -> dict[str, Any] | None:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def pack_audio_chunk(session_bytes: bytes, seq: int, total: int, payload: bytes) -> bytes:
    if len(session_bytes) != 16:
        raise ValueError("session_bytes debe contener 16 bytes")
    if len(payload) > CHUNK_SIZE:
        raise ValueError("fragmento de audio demasiado grande")
    return _HEADER.pack(
        MAGIC,
        VERSION,
        TYPE_AUDIO_CHUNK,
        session_bytes,
        seq,
        total,
        len(payload),
    ) + payload


def unpack_audio_chunk(data: bytes) -> tuple[bytes, int, int, bytes] | None:
    if len(data) < _HEADER.size:
        return None
    magic, version, packet_type, session, seq, total, payload_len = _HEADER.unpack_from(data)
    if magic != MAGIC or version != VERSION or packet_type != TYPE_AUDIO_CHUNK:
        return None
    payload = data[_HEADER.size:]
    if len(payload) != payload_len:
        return None
    return session, seq, total, payload
