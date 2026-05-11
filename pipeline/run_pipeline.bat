@echo off
REM ============================================================
REM  Weekly SQL -> Excel -> PowerPoint pipeline runner
REM  Called by Windows Task Scheduler every Monday.
REM  Log output appended to pipeline\pipeline.log
REM ============================================================

setlocal

REM Resolve the directory this .bat lives in
set "SCRIPT_DIR=%~dp0"

REM ---- Python interpreter ----
REM  Priority 1: virtualenv inside pipeline\venv\
REM  Priority 2: system / PATH Python
if exist "%SCRIPT_DIR%venv\Scripts\python.exe" (
    set "PYTHON=%SCRIPT_DIR%venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)

echo [%DATE% %TIME%] Starting pipeline... >> "%SCRIPT_DIR%pipeline.log"

"%PYTHON%" "%SCRIPT_DIR%sql_to_pptx.py" >> "%SCRIPT_DIR%pipeline.log" 2>&1

if %ERRORLEVEL% NEQ 0 (
    echo [%DATE% %TIME%] ERROR: pipeline exited with code %ERRORLEVEL% >> "%SCRIPT_DIR%pipeline.log"
    exit /b %ERRORLEVEL%
)

echo [%DATE% %TIME%] Pipeline finished successfully. >> "%SCRIPT_DIR%pipeline.log"
endlocal
