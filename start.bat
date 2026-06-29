@echo off
echo Activating Virtual Environment...
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)
echo Starting Invisible AI Control Hub...
start /B pythonw manager.py
exit
