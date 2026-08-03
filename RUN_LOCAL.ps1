param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$ProjectDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDirectory

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python is not installed or is not available in PATH. Install Python 3.12 and run the script again."
}

if (-not (Test-Path ".venv")) {
    Write-Host "Creating a Python virtual environment ..."
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the Python virtual environment."
    }
}

$Python = Join-Path $ProjectDirectory ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "The Python virtual environment is incomplete. Delete .venv and run the script again."
}

if (-not $SkipInstall) {
    Write-Host "Installing dependencies ..."
    & $Python -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "Could not update pip." }
    & $Python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "Could not install the project dependencies." }
}

Write-Host "Starting Streamlit ..."
& $Python -m streamlit run app.py
