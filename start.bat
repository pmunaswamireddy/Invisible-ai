@echo off
echo Starting Invisible AI Overlay...
.venv\Scripts\python.exe -u overlay.py > error.log 2>&1
exit
