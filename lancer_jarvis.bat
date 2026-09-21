@echo off
title Jarvis
rem Lanceur de l'assistant vocal. Se place dans le dossier du projet puis
rem demarre jarvis14.py via uv. Chemin absolu vers uv pour fonctionner
rem aussi au demarrage de Windows, ou le PATH peut differer.
cd /d "%~dp0"
git pull --ff-only 2>nul
"%USERPROFILE%\.local\bin\uv.exe" run python jarvis14.py
echo.
echo Jarvis s'est arrete. Vous pouvez fermer cette fenetre.
pause
