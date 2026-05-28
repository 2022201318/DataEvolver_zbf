@echo off
REM DataEvolver — Windows CMD bootstrap (delegates to scripts/setup_env.py)
setlocal
cd /d "%~dp0"

if defined PYTHON_BIN (
  set "PY=%PYTHON_BIN%"
) else (
  where python >nul 2>&1 && set "PY=python" && goto :run
  where py >nul 2>&1 && set "PY=py -3" && goto :run
  echo Python 3.10+ is required. Install from https://www.python.org/downloads/
  exit /b 1
)

:run
%PY% scripts\setup_env.py %*
exit /b %ERRORLEVEL%
