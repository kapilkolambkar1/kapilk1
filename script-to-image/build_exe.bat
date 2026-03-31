@echo off
REM ============================================================
REM build_exe.bat  --  Build the Script-to-Image executable (Windows)
REM ============================================================
REM Usage:
REM   Double-click this file or run from Command Prompt:
REM     build_exe.bat
REM
REM Output:
REM   dist\ScriptToImage\ScriptToImage.exe
REM ============================================================

echo =^> Installing dependencies...
pip install -r requirements.txt
pip install pyinstaller

echo =^> Running PyInstaller...
pyinstaller ScriptToImage.spec --clean --noconfirm

echo.
echo =====================================================
echo   Build complete!
echo   Executable: dist\ScriptToImage\ScriptToImage.exe
echo =====================================================
echo.
echo To run, copy your .env file first:
echo   copy .env dist\ScriptToImage\.env
echo Then double-click:
echo   dist\ScriptToImage\ScriptToImage.exe
echo.
pause
