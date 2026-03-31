# PyInstaller spec file for Script-to-Image Generator
# Build with:
#   pip install pyinstaller
#   pyinstaller ScriptToImage.spec

import os
from pathlib import Path

ROOT = Path(SPECPATH)

block_cipher = None

a = Analysis(
    [str(ROOT / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # Bundle the Streamlit app and all source modules
        (str(ROOT / "app.py"),             "."),
        (str(ROOT / "config.py"),           "."),
        (str(ROOT / "models"),              "models"),
        (str(ROOT / "generators"),          "generators"),
        (str(ROOT / "examples"),            "examples"),
        (str(ROOT / ".env.example"),        "."),
        # Streamlit static assets
        (os.path.join(os.path.dirname(__import__("streamlit").__file__), "static"),
         "streamlit/static"),
        (os.path.join(os.path.dirname(__import__("streamlit").__file__), "runtime"),
         "streamlit/runtime"),
    ],
    hiddenimports=[
        # Streamlit internals
        "streamlit",
        "streamlit.web.cli",
        "streamlit.web.server",
        "streamlit.runtime.scriptrunner",
        # Our modules
        "models",
        "models.character",
        "models.location",
        "models.script",
        "generators",
        "generators.prompt_generator",
        "generators.image_generator",
        # Dependencies
        "anthropic",
        "replicate",
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",
        "dotenv",
        "click",
        "requests",
        "rich",
        "altair",
        "pydeck",
        "pyarrow",
        "validators",
        "packaging",
        "importlib_metadata",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "torch", "torchvision", "tensorflow",
        "matplotlib", "scipy", "sklearn",
    ],
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
    name="ScriptToImage",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,           # No terminal window on Windows
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,               # Add an .ico path here if you have one
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ScriptToImage",
)
