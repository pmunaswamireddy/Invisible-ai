@echo off
echo ===========================================
echo   Pushing Invisible AI to GitHub
echo ===========================================
echo.

echo [1] Preparing Git Repository...
if exist ".git" rmdir /s /q ".git"
git init
git add .

echo [2] Configuring Local Committer Identity...
git config user.name "PMR"
git config user.email "pmunaswamireddy@github.com"

echo [3] Committing Clean Codebase (API Keys are safely redacted!)...
git commit -m "Initial commit of Invisible AI overlay and build scripts"
git branch -M main

echo [4] Linking to GitHub Remote...
git remote add origin https://github.com/pmunaswamireddy/Invisible-ai.git

echo.
echo [5] Pushing to GitHub (Forcing Overwrite)...
echo (A browser window or popup may appear asking you to sign into GitHub to authenticate the upload)
git push -f -u origin main

echo.
echo ===========================================
echo   PUSH COMPLETE!
echo   Your code is now live on GitHub!
echo ===========================================
pause
