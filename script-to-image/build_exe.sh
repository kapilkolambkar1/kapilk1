#!/usr/bin/env bash
# ============================================================
# build_exe.sh  —  Build the Script-to-Image executable
# ============================================================
# Usage:
#   chmod +x build_exe.sh
#   ./build_exe.sh
#
# Output:
#   dist/ScriptToImage/ScriptToImage        (Linux/macOS)
#   dist/ScriptToImage/ScriptToImage.exe    (Windows via Wine or native)
# ============================================================

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "==> Installing dependencies..."
pip install -r requirements.txt
pip install pyinstaller

echo "==> Running PyInstaller..."
pyinstaller ScriptToImage.spec --clean --noconfirm

echo ""
echo "====================================================="
echo "  Build complete!"
echo "  Executable: dist/ScriptToImage/ScriptToImage"
echo "====================================================="
echo ""
echo "To run:"
echo "  ./dist/ScriptToImage/ScriptToImage"
echo ""
echo "Copy your .env file next to the executable before running:"
echo "  cp .env dist/ScriptToImage/.env"
