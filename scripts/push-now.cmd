@echo off
cd /d "%~dp0.."
echo Pushing BotFuther to https://github.com/BnayaG1/BotFuther
echo A GitHub login window may appear.
powershell -ExecutionPolicy Bypass -File "%~dp0publish-github.ps1" -ForceMain
pause
