"""
Path resolution and sys.path setup.
Allows importing from live/ and lib/ without restructuring.
"""

import sys
from pathlib import Path

# trading-strategies/
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Add live/ and lib/ to sys.path so existing imports work
LIVE_DIR = REPO_ROOT / "live"
LIB_DIR = REPO_ROOT / "lib"
CONFIG_DIR = REPO_ROOT / "config"
EXPORTS_DIR = REPO_ROOT / "strategy_exports"

for p in [str(LIVE_DIR), str(LIB_DIR), str(REPO_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)
