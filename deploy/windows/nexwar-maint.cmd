@echo off
rem Double-click: stop our software on the robot (see nexwar-maint.ps1). Needs the robot Wi-Fi.
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0nexwar-maint.ps1" %*
echo.
pause
