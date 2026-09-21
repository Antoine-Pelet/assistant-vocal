@echo off
title Red - Assistant vocal local
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\lancer_red.ps1"
echo.
echo Red s'est arrete. Vous pouvez fermer cette fenetre.
pause
