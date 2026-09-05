@echo off
setlocal
cd /d "%~dp0"
echo MCR R8 target-Windows qualification starting...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0RUN_TARGET_WINDOWS_QUALIFICATION.ps1"
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
  echo PASS. Upload the MCR_R8_TARGET_WINDOWS_RESULTS_TO_UPLOAD_*.zip file created in this folder.
) else (
  echo FAIL. Upload the MCR_R8_TARGET_WINDOWS_RESULTS_TO_UPLOAD_*.zip file created in this folder.
)
echo.
pause
exit /b %RC%
