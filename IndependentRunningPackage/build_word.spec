# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['d:\\Trae_Project\\agent\\IndependentRunningPackage\\build_word_from_templates.py'],
    pathex=[],
    binaries=[],
    datas=[('d:\\Trae_Project\\agent\\IndependentRunningPackage\\templates', 'templates'), ('d:\\Trae_Project\\agent\\IndependentRunningPackage\\data', 'data')],
    hiddenimports=[],
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
    name='build_word',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
