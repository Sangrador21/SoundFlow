"""Copia solo los archivos del manifiesto a una biblioteca generada por nodo."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil

MARKER = '.soundflow-generated.json'
EXTENSIONS = {'.mp3', '.wav', '.ogg', '.flac'}
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def names_from(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, list) or not data:
        raise ValueError('El manifiesto debe contener una lista de nombres de archivo.')
    for value in data:
        if (not isinstance(value, str) or Path(value).name != value or '\\' in value
                or Path(value).suffix.lower() not in EXTENSIONS):
            raise ValueError('Cada entrada debe ser un nombre de audio sin rutas.')
    return list(dict.fromkeys(data))


def build_catalog(source: Path, manifest: Path, output: Path) -> list[str]:
    names = names_from(manifest)
    source, output = source.resolve(), output.resolve()
    if source == output or source in output.parents:
        raise ValueError('La salida debe estar separada de la biblioteca de origen.')
    for name in names:
        if not (source / name).is_file() or (source / name).is_symlink():
            raise ValueError(f'No existe el archivo de origen: {name}')
    previous = names_from(output / MARKER) if (output / MARKER).exists() else []
    if output.exists():
        unmanaged = [p for p in output.iterdir() if p.name not in {*previous, MARKER}]
        if unmanaged:
            raise ValueError('La salida contiene archivos ajenos. Utiliza una carpeta generada vacía.')
    output.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.copy2(source / name, output / name)
    for name in set(previous) - set(names):
        (output / name).unlink(missing_ok=True)
    (output / MARKER).write_text(json.dumps(names, ensure_ascii=False), encoding='utf-8')
    return names


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node', choices=['S1', 'S2'])
    parser.add_argument('--source', type=Path, default=PROJECT_ROOT / 'music')
    parser.add_argument('--output', type=Path, default=PROJECT_ROOT / '.local_music')
    args = parser.parse_args()
    for node in [args.node] if args.node else ['S1', 'S2']:
        songs = build_catalog(args.source, PROJECT_ROOT / 'deploy' / 'catalogs' / f'{node}.json', args.output / node)
        print(f'{node}: {len(songs)} canciones preparadas en {args.output / node}')
