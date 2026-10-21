# Start Polarity and open the browser (Windows). Extra arguments are passed to `polarity run`,
# e.g.  scripts\run_windows.ps1 --role hub
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root
$env:PYTHONIOENCODING = "utf-8"
$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPy)) {
    Write-Host "No .venv found. Run scripts\setup_windows.bat first." -ForegroundColor Yellow
    exit 1
}
& $VenvPy -m polarity run --open-browser @args
exit $LASTEXITCODE
