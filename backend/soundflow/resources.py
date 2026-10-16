"""Métricas de host o cgroup: los contenedores tienen su propia cuota de recursos."""
from __future__ import annotations

from pathlib import Path
import time

import psutil


class ResourceMonitor:
    def __init__(self, root: Path = Path('/sys/fs/cgroup')) -> None:
        self.root = root
        self.previous: tuple[float, int] | None = None
        psutil.cpu_percent(interval=None)

    def sample(self) -> tuple[float, float]:
        cpu = psutil.cpu_percent(interval=None)
        memory = psutil.virtual_memory().percent
        try:
            limit = int((self.root / 'memory.max').read_text().strip())
            used = int((self.root / 'memory.current').read_text().strip())
            if limit > 0:
                memory = min(100, used / limit * 100)
        except (OSError, ValueError):
            pass
        try:
            quota, period = (self.root / 'cpu.max').read_text().split()
            usage = dict(line.split() for line in (self.root / 'cpu.stat').read_text().splitlines())
            current = (time.monotonic(), int(usage['usage_usec']))
            if quota != 'max' and int(quota) > 0 and self.previous:
                seconds = current[0] - self.previous[0]
                if seconds > 0:
                    cpu = max(0, min(100, (current[1] - self.previous[1]) / 1_000_000
                                     / seconds / (int(quota) / int(period)) * 100))
            self.previous = current
        except (OSError, ValueError, KeyError, ZeroDivisionError):
            pass
        return cpu, memory
