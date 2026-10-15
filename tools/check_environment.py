import importlib
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

print('Python:', sys.version.split()[0])
failed = False
for name in ['flask', 'requests', 'mutagen', 'pygame', 'pygame.mixer', 'psutil',
             'imageio_ffmpeg', 'cryptography', 'tkinter']:
    try:
        importlib.import_module(name)
        print(name + ': OK')
    except ImportError as exc:
        failed = True
        print(name + ': FALTA — ' + str(exc))
try:
    from soundflow.audio import ffmpeg_executable
    print('FFmpeg:', ffmpeg_executable())
except Exception as exc:
    failed = True
    print('FFmpeg: ' + str(exc))
if failed:
    print('Si falta pygame.mixer, pygame se instaló sin el componente de audio.')
    print('En Mac instala SDL2_mixer y vuelve a compilar pygame sin usar su caché.')
    sys.exit(1)
print('Entorno preparado. Tkinter requiere sesión gráfica; pygame requiere salida de audio.')
