"""
Eye Tracker Setup Script
========================
Run this ONCE after cloning the repo and installing requirements.
It patches the installed ptgaze package with the fixed files from this repo.

Usage:
    python setup.py

Requirements:
    - Python 3.11
    - pip install -r requirements.txt  (run this first)
"""

import sys
import shutil
import subprocess
import importlib.util
from pathlib import Path

# ── Colours for terminal output ──────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
RESET  = "\033[0m"

def ok(msg):   print(f"{GREEN}  [OK]{RESET} {msg}")
def warn(msg): print(f"{YELLOW}  [!!]{RESET} {msg}")
def err(msg):  print(f"{RED}  [ERR]{RESET} {msg}")
def info(msg): print(f"  --> {msg}")

print("")
print("=" * 55)
print("  Eye Tracker — Automated Setup")
print("=" * 55)
print("")

# ── 1. Check Python version ──────────────────────────────────────────────────
print("[1/5] Checking Python version...")
major, minor = sys.version_info.major, sys.version_info.minor
if major == 3 and minor == 11:
    ok(f"Python {major}.{minor} detected.")
else:
    warn(f"Python {major}.{minor} detected. Python 3.11 is recommended.")
    warn("Some dependencies may not work correctly on other versions.")

# ── 2. Find ptgaze install location ──────────────────────────────────────────
print("")
print("[2/5] Locating installed ptgaze...")
spec = importlib.util.find_spec("ptgaze")
if spec is None:
    err("ptgaze is not installed. Run: pip install -r requirements.txt first.")
    sys.exit(1)

ptgaze_path = Path(spec.origin).parent
ok(f"Found ptgaze at: {ptgaze_path}")

# ── 3. Locate patched files in this repo ─────────────────────────────────────
print("")
print("[3/5] Locating patched ptgaze files in this repo...")
repo_root   = Path(__file__).parent
patched_dir = repo_root / "ptgaze_patched"

if not patched_dir.exists():
    err(f"'ptgaze_patched' folder not found at: {patched_dir}")
    err("Make sure you cloned the full repository.")
    sys.exit(1)

patched_files = list(patched_dir.rglob("*.py"))
ok(f"Found {len(patched_files)} patched file(s) in ptgaze_patched/")

# ── 4. Apply patches ──────────────────────────────────────────────────────────
print("")
print("[4/5] Applying patches to installed ptgaze...")

success = 0
failed  = 0

for src in patched_files:
    # Compute relative path inside ptgaze_patched/
    rel = src.relative_to(patched_dir)
    dst = ptgaze_path / rel

    if not dst.parent.exists():
        warn(f"Skipping {rel} — destination folder doesn't exist.")
        continue

    try:
        # Back up original if not already backed up
        bak = dst.with_suffix(".py.bak")
        if not bak.exists():
            shutil.copy2(dst, bak)

        shutil.copy2(src, dst)
        ok(f"Patched: {rel}")
        success += 1
    except Exception as e:
        err(f"Failed to patch {rel}: {e}")
        failed += 1

print("")
if failed == 0:
    ok(f"All {success} file(s) patched successfully.")
else:
    warn(f"{success} patched, {failed} failed.")

# ── 5. Verify import ──────────────────────────────────────────────────────────
print("")
print("[5/5] Verifying ptgaze import...")
try:
    from ptgaze.gaze_estimator import GazeEstimator
    ok("ptgaze imports successfully.")
except Exception as e:
    err(f"ptgaze import failed: {e}")
    err("Check the patches manually.")
    sys.exit(1)

# ── Done ──────────────────────────────────────────────────────────────────────
print("")
print("=" * 55)
print(f"{GREEN}  Setup complete! You can now run: python main.py{RESET}")
print("=" * 55)
print("")
print("  Notes:")
print("  - mediapipe must be 0.10.9 (pinned in requirements.txt)")
print("  - ptgaze runs on CPU if no NVIDIA GPU is available")
print("  - ETH-XGaze model downloads automatically on first run")
print("")
