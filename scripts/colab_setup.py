"""
Colab Setup — Run this cell first in any Colab session.
Clones/pulls the repo, installs deps, and mounts Google Drive.

Usage (paste in Colab cell):
    !git clone https://github.com/r-giov/trading-strategies.git 2>/dev/null; cd trading-strategies && git pull
    %run scripts/colab_setup.py
"""

import subprocess, sys, os

# ── Install dependencies ──
DEPS = ["yfinance", "TA-Lib", "vectorbt", "scipy"]
for pkg in DEPS:
    try:
        __import__(pkg.lower().replace("-", ""))
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", pkg])

# TA-Lib needs the C library on Colab
try:
    import talib
except ImportError:
    print("Installing TA-Lib C library...")
    subprocess.run("apt-get install -y -qq libta-lib0 libta-lib-dev", shell=True, capture_output=True)
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "TA-Lib"])

# ── Mount Google Drive ──
try:
    from google.colab import drive
    if not os.path.exists('/content/drive/MyDrive'):
        drive.mount('/content/drive')
    EXPORT_DIR = "/content/drive/MyDrive/strategy_exports"
    os.makedirs(EXPORT_DIR, exist_ok=True)
    print(f"Drive mounted. Exports → {EXPORT_DIR}")
except ImportError:
    print("Not on Colab — skipping Drive mount.")

# ── Verify imports ──
import yfinance, talib, numpy, pandas, vectorbt, scipy, matplotlib
print(f"All deps loaded. vectorbt={vectorbt.__version__}, talib={talib.__version__}")
print("Ready to run notebooks.")
