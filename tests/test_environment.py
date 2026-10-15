import importlib
from pathlib import Path
import runpy
import pytest


def test_environment_check_detects_missing_optional_mixer(monkeypatch, capsys):
    original = importlib.import_module

    def import_without_mixer(name, *args, **kwargs):
        if name == 'pygame.mixer':
            raise ModuleNotFoundError("No module named 'pygame.mixer'")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(importlib, 'import_module', import_without_mixer)
    with pytest.raises(SystemExit) as error:
        runpy.run_path(str(Path(__file__).parents[1] / 'tools' / 'check_environment.py'))
    assert error.value.code == 1
    assert 'pygame.mixer: FALTA' in capsys.readouterr().out
