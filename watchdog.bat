@echo off
setlocal
echo KIBERone Watchdog Started
echo Monitoring KIBERoneStudent.exe...

:loop
tasklist | find /i "KIBERoneStudent.exe" > nul
if errorlevel 1 (
    echo [%time%] KIBERoneStudent.exe not found! Restarting...
    set KIBERONE_WATCHDOG_RECOVERED=1
    start "" "KIBERoneStudent.exe"
)
timeout /t 5 /nobreak > nul
goto loop
