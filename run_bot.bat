@echo off
title botthehekli

:loop
echo Starting Bot...
python main.py

if %ERRORLEVEL% EQU 42 (
    echo [RESTART REQUESTED] Restarting bot in 2 seconds...
    timeout /t 2 >nul
    goto loop
)

echo Bot exited with code %ERRORLEVEL%.
pause
