# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Treningsanalyse desktop backend (Windows x64)."""

from pathlib import Path

block_cipher = None
# SPECPATH is backend/packaging → backend root is parent
backend = Path(SPECPATH).resolve().parent

a = Analysis(
    [str(backend / "app" / "desktop_backend.py")],
    pathex=[str(backend)],
    binaries=[],
    datas=[
        (str(backend / "alembic"), "alembic"),
        (str(backend / "alembic.ini"), "."),
        (str(backend / "app"), "app"),
    ],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "sqlalchemy.dialects.sqlite",
        "alembic",
        "pydantic_settings",
        "multipart",
        "garminconnect",
        "fitparse",
        "polars",
        "pyarrow",
        "plotly",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="treningsanalyse-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
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
    upx=True,
    upx_exclude=[],
    name="treningsanalyse-backend",
)
