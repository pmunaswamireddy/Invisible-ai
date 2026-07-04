@echo off
echo ===========================================
echo   Building Invisible AI Executable & Git
echo ===========================================
echo.

echo [1] Activating Virtual Environment...
call .venv\Scripts\activate.bat

echo [2] Installing Dependencies...
pip install pyinstaller python-dotenv googlesearch-python pygments



echo.
set /p VERSION="Enter version name/folder (e.g., v4): "
if "%VERSION%"=="" set VERSION=v4

echo [4] Cleaning previous builds...
if exist "build" rmdir /s /q "build"

echo [5] Compiling to standalone executable in dist\%VERSION% using optimized spec file...
pyinstaller --distpath dist\%VERSION% SystemAudioEngine.spec

echo [6] Building complete!
echo.
echo ===========================================
echo   BUILD COMPLETE!
echo   Your executable is located in 'dist\%VERSION%' folder.
echo ===========================================
echo.
set /p CHOICE="Do you want to self-sign the executable to bypass Windows SmartScreen? (y/n): "
if /I "%CHOICE%"=="Y" (
    echo.
    echo Running self_sign.ps1 as Administrator for dist/%VERSION%/SystemAudioEngine.exe...
    powershell -Command "Start-Process powershell -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File self_sign.ps1 -exePath dist/%VERSION%/SystemAudioEngine.exe' -Verb RunAs"
)
pause
