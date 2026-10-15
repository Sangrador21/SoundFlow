"""Formato común de audio para streaming y búsqueda por tiempo."""
from __future__ import annotations

import shutil

SAMPLE_RATE = 44100
CHANNELS = 2
SAMPLE_BYTES = 2  # PCM firmado little-endian de 16 bits
FRAME_BYTES = CHANNELS * SAMPLE_BYTES
BYTES_PER_SECOND = SAMPLE_RATE * FRAME_BYTES
CHUNK_BYTES = 16 * 1024
BUFFER_SECONDS = 1.0


def ffmpeg_executable() -> str:
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()
