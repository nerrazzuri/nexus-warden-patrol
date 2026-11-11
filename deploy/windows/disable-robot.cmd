@echo off
rem Double-click: disable our software on the robot (see disable-robot.ps1). Needs the robot Wi-Fi.
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0disable-robot.ps1" %*
echo.
pause
