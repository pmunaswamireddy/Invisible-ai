@echo off
echo ===========================================
echo   Building Invisible AI Executable & Git
echo ===========================================
echo.

echo [1] Activating Virtual Environment...
call .venv\Scripts\activate.bat

echo [2] Installing Dependencies...
pip install pyinstaller python-dotenv



echo [4] Cleaning previous builds...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "*.spec" del /q "*.spec"

echo [5] Compiling to standalone executable...
pyinstaller --onefile --windowed --name "SystemAudioEngine" --add-data ".env;." --hidden-import pyttsx3.drivers --hidden-import pyttsx3.drivers.sapi5 overlay.py

echo.
echo ===========================================
echo   BUILD COMPLETE!
echo   Your executable is located in the 'dist' folder.
echo ===========================================
pause
