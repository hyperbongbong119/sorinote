"""Bundled assets are read-only; credentials and recordings live outside the EXE."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FROZEN = bool(getattr(sys, 'frozen', False))
HOME = Path(os.getenv('SORINOTE_HOME') or (Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'Sorinote' if FROZEN else ROOT)).resolve()
ENV_FILE = Path(os.getenv('SORINOTE_ENV_FILE') or HOME / '.env.local').resolve()
DATA_DIR = Path(os.getenv('SORINOTE_DATA_DIR') or HOME / 'data').resolve()


def prepare():
    HOME.mkdir(parents=True, exist_ok=True)
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not ENV_FILE.exists():
        ENV_FILE.touch(exist_ok=True)

