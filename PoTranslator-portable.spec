# -*- mode: python ; coding: utf-8 -*-
# ============================================================================
#  PoTranslator-portable.spec - variante portable de CARPETA (onedir)
#
#  Compila la app como una carpeta (no autoextraíble):
#      pyinstaller PoTranslator-portable.spec --noconfirm
#
#  Resultado:  dist/PoTranslator/PoTranslator.exe + archivos de apoyo
#  (en GitHub Actions se comprime como PoTranslator-portable-win64.zip)
#
#  Por que existe: el .exe de archivo unico (onefile) se autodescomprime
#  en %TEMP% al arrancar y muchos antivirus lo marcan por eso
#  ("BehavesLike.Win64...", "Gen:Variant.Yogi..."). La variante de carpeta
#  NO se autodescomprime y suele pasar los escaneos casi limpia.
#  Uso: descomprimir el ZIP y ejecutar PoTranslator\PoTranslator.exe.
#
#  - polib.py se empaqueta solo (esta junto al script y se importa normal)
#  - upx=False y version.txt por lo mismo que en PoTranslator.spec
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
    [],
    exclude_binaries=True,
    name='PoTranslator',
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
    icon='icono.ico',
    version='version.txt',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='PoTranslator',
)
