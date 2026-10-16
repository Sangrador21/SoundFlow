"""Comprueba las dependencias del backend web; no requiere Tkinter ni pygame."""
import importlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))


def check() -> bool:
    success = True
    for name in ['flask', 'flask_cors', 'requests', 'mutagen', 'psutil', 'cryptography', 'dotenv']:
        try:
            importlib.import_module(name)
            print(f'OK: {name}')
        except ImportError as error:
            print(f'FALTA: {name}: {error}')
            success = False
    try:
        from soundflow.audio import ffmpeg_executable
        import subprocess
        subprocess.run([ffmpeg_executable(), '-version'], capture_output=True, check=True)
        print('OK: FFmpeg')
    except Exception as error:
        print(f'FALTA: FFmpeg: {error}')
        success = False
    return success


if __name__ == '__main__':
    raise SystemExit(0 if check() else 1)
