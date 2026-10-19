# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Image Sorter - portable one-folder build."""

import sys, os
from pathlib import Path

block_cipher = None

ROOT = Path('.').resolve()
SRC = ROOT / 'src'
ASSETS = SRC / 'assets'
FONT = ASSETS / 'fonts' / 'NotoSansCJKsc-Regular.otf'
ICON = ASSETS / 'icons' / 'app.ico'

a = Analysis(
    [str(SRC / 'main.py')],
    pathex=[str(SRC), str(ROOT)],
    binaries=[],

    datas=[
        (str(FONT), 'src/assets/fonts'),
        (str(ASSETS / 'icons' / 'app.png'), 'src/assets/icons'),
    ],
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'pillow_heif',
        'rawpy',
        'send2trash',
        'numpy',
        'pefile',
        'tools.patch_qt6core',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'matplotlib', 'pandas',
        'PySide6.QtNetwork', 'PySide6.QtWebEngine',
        'PySide6.Qt3DCore', 'PySide6.Qt3DRender',
        'PySide6.QtCharts', 'PySide6.QtDataVisualization',
        'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets',
        'PySide6.QtPositioning', 'PySide6.QtPrintSupport',
        'PySide6.QtSensors', 'PySide6.QtSerialPort',
        'PySide6.QtSql', 'PySide6.QtTest', 'PySide6.QtWebChannel',
        'PySide6.QtWebSockets',
    ],
    win_no_prefer_redirects=False,
    
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ImageSort',
    icon=str(ICON),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='ImageSort',
)
