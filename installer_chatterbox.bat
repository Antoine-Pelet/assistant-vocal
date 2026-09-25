@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\installer_chatterbox.ps1" %*
if errorlevel 1 (
  echo Installation incomplete. Consulte le message ci-dessus.
  pause
  exit /b 1
)
pause
