@echo off
REM ============================================================
REM  build_exe.bat  --  Build Script-to-Image for Windows
REM ============================================================
REM  Prerequisites:
REM    Python 3.10+ (64-bit) must be in PATH
REM    Run from the project root directory
REM
REM  Usage:
REM    Double-click this file  OR  run from Command Prompt:
REM      build_exe.bat
REM
REM  Output:
REM    dist\ScriptToImage\ScriptToImage.exe
REM ============================================================

setlocal enabledelayedexpansion

echo.
echo  ========================================================
echo   Script-to-Image Generator ^| Windows Build
echo  ========================================================
echo.

REM ── Check Python ──────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found. Install Python 3.10+ from python.org
    pause
    exit /b 1
)
echo  [OK] Python found.

REM ── Upgrade pip ───────────────────────────────────────────
echo.
echo  [1/4] Upgrading pip...
python -m pip install --upgrade pip --quiet

REM ── Install runtime dependencies ──────────────────────────
echo  [2/4] Installing dependencies...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo  [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
echo  [OK] Dependencies installed.

REM ── Install PyInstaller ───────────────────────────────────
echo  [3/4] Installing PyInstaller...
pip install pyinstaller>=6.0 --quiet
if errorlevel 1 (
    echo  [ERROR] Failed to install PyInstaller.
    pause
    exit /b 1
)
echo  [OK] PyInstaller ready.

REM ── Build ─────────────────────────────────────────────────
echo  [4/4] Building executable (this may take 2-5 minutes)...
echo.
pyinstaller ScriptToImage.spec --clean --noconfirm
if errorlevel 1 (
    echo.
    echo  [ERROR] PyInstaller build failed. See output above.
    pause
    exit /b 1
)

REM ── Post-build: copy .env.example ─────────────────────────
if exist ".env.example" (
    copy /Y ".env.example" "dist\ScriptToImage\.env.example" >nul
)

echo.
echo  ========================================================
echo   BUILD COMPLETE
echo  ========================================================
echo.
echo   Executable : dist\ScriptToImage\ScriptToImage.exe
echo   Folder     : dist\ScriptToImage\
echo.
echo  HOW TO RUN:
echo   1. Copy your API keys file:
echo         copy .env dist\ScriptToImage\.env
echo   2. Double-click:
echo         dist\ScriptToImage\ScriptToImage.exe
echo.
echo  DISTRIBUTE:
echo   Zip the entire dist\ScriptToImage\ folder and share it.
echo   The recipient does NOT need Python installed.
echo.
pause
