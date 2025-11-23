# -*- mode: python ; coding: utf-8 -*-

import enchant
from importlib import resources

try:
    enchant_data_dir = resources.files(enchant) / 'data'
    enchant_datas = [
        (
            str(enchant_data_dir),
            'enchant/data',
        )
    ] if enchant_data_dir.is_dir() else []
except (FileNotFoundError, ModuleNotFoundError, AttributeError):
    enchant_datas = []

a = Analysis(
    ['fimpad/__main__.py'],
    pathex=[],
    binaries=[],
    datas=[
        (
            'fimpad/library',
            'fimpad/library',
        ),
        *enchant_datas,
    ],
    # Ship enchant dictionaries with the bundle so spellcheck works without
    # relying on an external enchant installation.
    hiddenimports=[
        'tkinter',
        'tkinter.scrolledtext',
        'enchant',
        'enchant.backends',
        'enchant.checker',
        'enchant.tokenize',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='fimpad',
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
)
