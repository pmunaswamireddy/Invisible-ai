@echo off
echo Cleaning up previous instances to free hotkeys...
taskkill /F /IM SystemAudioEngine.exe /T >nul 2>&1
taskkill /F /IM python.exe /T >nul 2>&1
taskkill /F /IM python3.13.exe /T >nul 2>&1

:: Check if virtual environment exists; if not, create it and install requirements automatically
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo [Setup] First-time run detected. Creating Python virtual environment...
    python -m venv "%~dp0.venv"
    echo [Setup] Installing required dependencies...
    "%~dp0.venv\Scripts\python.exe" -m pip install --upgrade pip
    "%~dp0.venv\Scripts\python.exe" -m pip install -r "%~dp0requirements.txt"
)

:: Truncate error.log if over 5 MB to prevent unbounded growth
for %%A in ("%~dp0error.log") do if %%~zA GTR 5242880 (
    echo [Log truncated at startup - was %%~zA bytes] > "%~dp0error.log"
)

echo Starting Invisible AI Overlay...
"%~dp0.venv\Scripts\python.exe" -u overlay.py
