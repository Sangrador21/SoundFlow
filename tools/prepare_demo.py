"""Tres tonos originales: uno compartido y uno exclusivo por servidor."""
from pathlib import Path
import argparse
import math
import struct
import wave


def tone(path: Path, frequency: float, seconds: float = 12) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rate = 44100
    data = bytearray()
    for i in range(int(rate * seconds)):
        # Desvanecimiento corto para evitar clicks al inicio/final.
        envelope = min(1, i / (rate * 0.03), (rate * seconds - i) / (rate * 0.03))
        sample = int(7000 * envelope * math.sin(2 * math.pi * frequency * i / rate))
        data.extend(struct.pack('<h', sample))
    with wave.open(str(path), 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(data)


def prepare(destination: Path) -> None:
    tone(destination / 'S1' / 'Exclusiva S1.wav', 440)
    tone(destination / 'S2' / 'Exclusiva S2.wav', 660)
    for node in ['S1', 'S2']:
        tone(destination / node / 'Compartida.wav', 550)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default='.demo_music')
    args = parser.parse_args()
    prepare(Path(args.out))
    print(f'Catálogos distintos preparados en {args.out}/S1 y {args.out}/S2')
