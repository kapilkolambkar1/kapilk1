# PyInstaller spec file for Script-to-Image Generator
# --------------------------------------------------------
# Build on Windows:
#   pip install pyinstaller
#   pyinstaller ScriptToImage.spec
#
# Output: dist\ScriptToImage\ScriptToImage.exe
# --------------------------------------------------------

import os
from pathlib import Path

ROOT = Path(SPECPATH)

block_cipher = None

a = Analysis(
    [str(ROOT / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # Core app files
        (str(ROOT / "gui_app.py"),          "."),
        (str(ROOT / "app.py"),              "."),
        (str(ROOT / "config.py"),           "."),
        # Modules
        (str(ROOT / "models"),              "models"),
        (str(ROOT / "generators"),          "generators"),
        (str(ROOT / "parsers"),             "parsers"),
        (str(ROOT / "examples"),            "examples"),
        (str(ROOT / ".env.example"),        "."),
        # Streamlit static assets (required for bundled exe)
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
        "streamlit.components.v1",
        # Our modules
        "models",
        "models.character",
        "models.location",
        "models.script",
        "generators",
        "generators.prompt_generator",
        "generators.image_generator",
        "generators.image_sheet",
        "generators.sheets_exporter",
        "generators.scene_image_pusher",
        "generators.video_generator",
        "parsers",
        "parsers.docx_parser",
        # python-docx internals
        "docx",
        "docx.oxml",
        "docx.oxml.ns",
        "docx.parts.document",
        "docx.parts.image",
        "lxml",
        "lxml.etree",
        "lxml._elementpath",
        # Google / gspread
        "gspread",
        "gspread.auth",
        "gspread_formatting",
        "google.auth",
        "google.auth.transport.requests",
        "google.oauth2.service_account",
        # AI & media
        "anthropic",
        "replicate",
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",
        "PIL.ImageFont",
        # Utilities
        "dotenv",
        "click",
        "requests",
        "rich",
        "pandas",
        # Streamlit extras
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
    icon=None,               # Set to "assets/icon.ico" if you add an icon
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
