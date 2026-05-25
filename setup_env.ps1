$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RootDir

function Resolve-Python {
    if ($env:PYTHON_BIN) {
        return $env:PYTHON_BIN
    }
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py) { return "python" }
    $py3 = Get-Command python3 -ErrorAction SilentlyContinue
    if ($py3) { return "python3" }
    throw "Python is not found in PATH. Please install Python 3.10+."
}

$PythonBin = Resolve-Python

Write-Host "[1/5] Create virtual environment (.venv)"
if (-not (Test-Path ".venv")) {
    & $PythonBin -m venv .venv
}

$ActivatePs1 = Join-Path $RootDir ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $ActivatePs1)) {
    throw "Cannot find activate script: $ActivatePs1"
}

. $ActivatePs1

Write-Host "[2/5] Upgrade pip"
python -m pip install --upgrade pip

Write-Host "[3/5] Install backend dependencies"
pip install -r requirements.txt
pip install -e .

Write-Host "[4/5] Prepare config templates"
if ((-not (Test-Path "config\api_config.json")) -and (Test-Path "config\api_config.example.json")) {
    Copy-Item "config\api_config.example.json" "config\api_config.json"
}
if ((-not (Test-Path "config\api_keys.json")) -and (Test-Path "config\api_keys.example.json")) {
    Copy-Item "config\api_keys.example.json" "config\api_keys.json"
}

Write-Host "[5/5] Install frontend dependencies"
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host ""
    Write-Host "npm is not found in PATH."
    Write-Host "Please install Node.js LTS (which includes npm), then reopen PowerShell and re-run:"
    Write-Host "  powershell -ExecutionPolicy Bypass -File .\setup_env.ps1"
    Write-Host ""
    Write-Host "Download: https://nodejs.org/"
    exit 1
}
Set-Location (Join-Path $RootDir "frontend")
if (Test-Path "package-lock.json") {
    npm ci
} else {
    npm install
}
Set-Location $RootDir

Write-Host ""
Write-Host "Environment is ready."
Write-Host "Next:"
Write-Host "  1) Fill API keys in config/api_config.json (and/or config/api_keys.json)."
Write-Host "  2) Start backend (PowerShell): .\.venv\Scripts\Activate.ps1; python run_server.py --reload"
Write-Host "  3) Start frontend: cd frontend; npm run dev"
