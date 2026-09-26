# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:/Users/Noah/Downloads/ai-coding-assistant-20260925T021859Z-1-001/ai-coding-assistant/AntlantisAFK/main.py'],
    pathex=[],
    binaries=[],
    datas=[('C:/Users/Noah/Downloads/ai-coding-assistant-20260925T021859Z-1-001/ai-coding-assistant/AntlantisAFK/assets', 'assets'), ('C:/Users/Noah/Downloads/ai-coding-assistant-20260925T021859Z-1-001/ai-coding-assistant/AntlantisAFK/build_runtime', 'runtime')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6.QtWebEngineCore', 'PySide6.Qt3DCore', 'PySide6.QtCharts', 'tkinter', 'test'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='AtlantisAFK',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['C:/Users/Noah/Downloads/ai-coding-assistant-20260925T021859Z-1-001/ai-coding-assistant/AntlantisAFK/assets/icon.ico'],
)
