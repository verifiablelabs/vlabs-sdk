"""Ensure src/ + the prm-eval tool are importable for local pytest runs."""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
for p in (_ROOT / "src", _ROOT / "tools" / "vlabs-prm-eval" / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
