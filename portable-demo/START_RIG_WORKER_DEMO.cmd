@echo off
setlocal
title Rig Worker Local AI Demo
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0RigWorkerDemo.ps1"
if errorlevel 1 (
  echo.
  echo Rig Worker Demo stopped with an error. Read the message above.
  pause
)
endlocal
