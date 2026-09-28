@echo off
REM Runs one Shorts Bot cycle. Point Windows Task Scheduler at this file.
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" bot.py run
) else (
    python bot.py run
)
