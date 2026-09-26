#!/usr/bin/env python3
"""Build the AntlantisAFK standalone Windows executable with PyInstaller.

Usage (from the project root, i.e. the folder containing main.py)::

    py -3 build.py            # one-file windowed exe
    py -3 build.py --console  # keep a console for debugging

The produced exe lands in ``dist/AntlantisAFK.exe``.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--console", action="store_true",
        help="Build a console build (default: windowed, no console).",
    )
    args = parser.parse_args()

    pyinstaller = shutil.which("pyinstaller") or shutil.which("pyinstaller.exe")
    if pyinstaller is None:
        print("PyInstaller not found. Run:  py -3 -m pip install pyinstaller")
        return 1

    worker = ROOT / "antlantisafk" / "minecraft" / "worker" / "afk_worker.js"
    if not worker.exists():
        print(f"Worker script missing: {worker}")
        return 1

    assets = ROOT / "assets"
    if not (assets / "icon.ico").exists():
        print(f"Brand assets missing in {assets} (icon.ico)")
        return 1

    cmd = [
        pyinstaller,
        "--onefile",
        "--name", "AntlantisAFK",
        "--clean",
        "--noconfirm",
        # Ship the worker script and brand assets inside the exe; the
        # bridge/theme unpack them via sys._MEIPASS at runtime.
        "--add-data", f"{worker};antlantisafk/minecraft/worker",
        "--add-data", f"{assets};assets",
        # PySide6 pulls in far more than we use; trim the biggest offenders.
        "--exclude-module", "PySide6.QtWebEngineCore",
        "--exclude-module", "PySide6.Qt3DCore",
        "--exclude-module", "PySide6.QtCharts",
        "--exclude-module", "tkinter",
        "--exclude-module", "test",
    ]
    if not args.console:
        cmd.append("--windowed")

    icon = ROOT / "assets" / "icon.ico"
    if icon.exists():
        cmd += ["--icon", str(icon)]
    else:
        print("note: assets/icon.ico not found; building without icon.")

    cmd.append(str(ROOT / "main.py"))

    print("+", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(ROOT))  # noqa: S603
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
