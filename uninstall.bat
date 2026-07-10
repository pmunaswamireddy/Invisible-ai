@echo off
echo ===========================================
echo   Uninstalling Invisible AI (SystemAudioEngine)
echo ===========================================
echo.

echo [1] Checking for running instances...
taskkill /F /IM SystemAudioEngine.exe /T 2>NUL
taskkill /F /IM python.exe /T 2>NUL

echo [2] Removing persistent AppData (Chat History, Settings, Images)...
if exist "%APPDATA%\InvisibleAI" (
    rmdir /S /Q "%APPDATA%\InvisibleAI"
    echo   - Successfully wiped AppData.
) else (
    echo   - No AppData found.
)

echo [3] Removing local source files...
cd ..
if exist "invisibleai" (
    rmdir /S /Q "invisibleai"
    echo   - Successfully wiped application directory.
)

echo.
echo ===========================================
echo   UNINSTALL COMPLETE! 
echo   All traces of Invisible AI have been removed from this system.
echo ===========================================
pause
