# -*- mode: python ; coding: utf-8 -*-
# ============================================================================
#  PoTranslator.spec - configuración de PyInstaller
#
#  Compila la app en un ÚNICO archivo ejecutable (sin consola):
#      pyinstaller PoTranslator.spec --noconfirm
#
#  Resultado:  dist/PoTranslator.exe   (Windows)
#  - polib.py se empaqueta solo (está junto al script y se importa normal)
#  - tkinter forma parte de Python estándar, no hay nada extra que añadir
#  - upx=False: evita falsos positivos de antivirus
#  - version.txt: metadatos del ejecutable (producto, autor, descripcion),
#    tambien reduce falsos positivos de antivirus
# ============================================================================


a = Analysis(
    ['po_translator.py'],
    pathex=[],
    binaries=[],
    datas=[],
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
    name='PoTranslator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icono.ico'],
    version='version.txt',
)
