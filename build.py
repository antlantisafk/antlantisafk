#!/usr/bin/env python3
"""Build the standalone AtlantisAFK.exe (PyInstaller, branded, self-contained).

Produces ``dist/AtlantisAFK.exe``: one file, wave icon, PySide6 GUI, and —
when ``--no-runtime`` is not passed — a **bundled Node.js runtime + worker
dependencies**, so end users need nothing but the exe itself.

Usage::

    py -3 build.py                # full standalone build (uses local Node if present)
    py -3 build.py --no-runtime   # smaller exe; requires Node.js on the user's PC

The bundled runtime lives in ``build_runtime/`` (node.exe + the worker's
node_modules). If it does not exist, this script assembles it from the local
Node installation (or downloads the official Node.js zip).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = ROOT / "build_runtime"
WORKER_DIR = ROOT / "antlantisafk" / "minecraft" / "worker"

# Official Node.js LTS (Windows x64) used when no local Node.exe is found.
NODE_VERSION = "v22.14.0"
NODE_ZIP_URL = (
    f"https://nodejs.org/dist/{NODE_VERSION}/node-{NODE_VERSION}-win-x64.zip"
)


def assemble_runtime() -> int:
    """Ensure ``build_runtime/`` holds node.exe + worker node_modules."""
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    worker_node_modules = WORKER_DIR / "node_modules"
    if not worker_node_modules.exists():
        print("Worker dependencies missing. Run first:")
        print(f"  cd {WORKER_DIR} && npm install")
        return 1

    node_exe = RUNTIME_DIR / "node.exe"
    if not node_exe.exists():
        local_node = shutil.which("node") or shutil.which("node.exe")
        if local_node:
            print(f"Copying local Node runtime: {local_node}")
            shutil.copy2(local_node, node_exe)
        else:
            print(f"Downloading Node.js {NODE_VERSION} (win-x64)…")
            zip_path = RUNTIME_DIR / "node.zip"
            urlretrieve(NODE_ZIP_URL, zip_path)  # noqa: S310 - fixed HTTPS URL
            with zipfile.ZipFile(zip_path) as zf:
                for member in zf.namelist():
                    if member.endswith("/node.exe"):
                        (RUNTIME_DIR / "node.exe").write_bytes(zf.read(member))
                        break
            zip_path.unlink(missing_ok=True)

    dest_modules = RUNTIME_DIR / "node_modules"
    if not dest_modules.exists():
        print("Copying worker dependencies (this can take a minute)…")
        shutil.copytree(worker_node_modules, dest_modules)

    # The worker script must sit inside runtime/ so require() resolves
    # node_modules from the same directory.
    shutil.copy2(WORKER_DIR / "afk_worker.js", RUNTIME_DIR / "afk_worker.js")
    shutil.copy2(WORKER_DIR / "package.json", RUNTIME_DIR / "package.json")
    print(f"Runtime ready in {RUNTIME_DIR}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-runtime", action="store_true",
        help="Skip bundling Node/worker deps (user must install Node.js).",
    )
    parser.add_argument(
        "--console", action="store_true",
        help="Build a console build (default: windowed).",
    )
    args = parser.parse_args()

    if not args.no_runtime:
        rc = assemble_runtime()
        if rc != 0:
            return rc

    pyinstaller = shutil.which("pyinstaller") or shutil.which("pyinstaller.exe")
    if pyinstaller is None:
        # pip --user installs the launcher outside PATH; use -m instead.
        probe = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "PyInstaller", "--version"],
            capture_output=True,
        )
        if probe.returncode != 0:
            print("PyInstaller not found. Run:  py -3 -m pip install pyinstaller")
            return 1
        pyinstaller_cmd = [sys.executable, "-m", "PyInstaller"]
    else:
        pyinstaller_cmd = [pyinstaller]

    icon = ROOT / "assets" / "icon.ico"
    if not icon.exists():
        print(f"Brand assets missing: {icon}")
        return 1

    cmd = [
        *pyinstaller_cmd,
        "--onefile",
        "--name", "AtlantisAFK",
        "--icon", str(icon),
        "--clean",
        "--noconfirm",
        # Brand assets (wave icon + wordmark) for the GUI.
        "--add-data", f"{ROOT / 'assets'};assets",
        "--exclude-module", "PySide6.QtWebEngineCore",
        "--exclude-module", "PySide6.Qt3DCore",
        "--exclude-module", "PySide6.QtCharts",
        "--exclude-module", "tkinter",
        "--exclude-module", "test",
    ]
    if not args.no_runtime:
        # The self-contained Node runtime + worker (found via sys._MEIPASS).
        cmd += ["--add-data", f"{RUNTIME_DIR};runtime"]
    else:
        worker = WORKER_DIR / "afk_worker.js"
        cmd += ["--add-data", f"{worker};antlantisafk/minecraft/worker"]
    if not args.console:
        cmd.append("--windowed")
    cmd.append(str(ROOT / "main.py"))

    print("+", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(ROOT))  # noqa: S603
    if result.returncode == 0:
        out = ROOT / "dist" / "AtlantisAFK.exe"
        size_mb = out.stat().st_size / (1024 * 1024) if out.exists() else 0
        print(f"\nBuilt {out} ({size_mb:.1f} MB)")
        print("Standalone: end users only need the exe"
              if not args.no_runtime else
              "NOTE: --no-runtime build requires Node.js on the user's PC.")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
