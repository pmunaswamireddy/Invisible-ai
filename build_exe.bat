@echo off
echo ===========================================
echo   Building Invisible AI Executable & Git
echo ===========================================
echo.

echo [1] Activating Virtual Environment...
call .venv\Scripts\activate.bat

echo [2] Installing Dependencies...
pip install pyinstaller python-dotenv googlesearch-python



echo [4] Cleaning previous builds...
if exist "build" rmdir /s /q "build"

echo [5] Compiling to standalone executable using optimized spec file...
pyinstaller SystemAudioEngine.spec

echo.
echo ===========================================
echo   BUILD COMPLETE!
echo   Your executable is located in the 'dist' folder.
echo ===========================================
pause
