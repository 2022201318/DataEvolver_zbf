# DataEvolver — Windows PowerShell bootstrap (delegates to scripts/setup_env.py)
$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RootDir

function Resolve-Python {
    if ($env:PYTHON_BIN) { return $env:PYTHON_BIN }
    if (Get-Command python -ErrorAction SilentlyContinue) { return "python" }
    if (Get-Command python3 -ErrorAction SilentlyContinue) { return "python3" }
    throw @"
Python 3.10+ is required.
Install from: https://www.python.org/downloads/
During setup, enable 'Add python.exe to PATH'.
"@
}

$PythonBin = Resolve-Python
& $PythonBin scripts/setup_env.py @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
