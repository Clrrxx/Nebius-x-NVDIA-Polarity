# One-time setup for Windows 10/11 x64: Python venv, dependencies, .env, demo scenes, doctor.
# Run via scripts\setup_windows.bat (handles the execution policy), or:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root
$env:PYTHONIOENCODING = "utf-8"

function Get-PyVersion([string]$Cmd, [string[]]$PyArgs) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $out = & $Cmd @PyArgs -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $out) { return $null }
        return ($out | Out-String).Trim()
    } catch {
        return $null
    } finally {
        $ErrorActionPreference = $previous
    }
}

function Invoke-Checked([string]$Exe, [string[]]$Arguments) {
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Command failed ($LASTEXITCODE): $Exe $($Arguments -join ' ')" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

$candidates = @(
    @{ Cmd = "py"; Args = @("-3.12") },
    @{ Cmd = "py"; Args = @("-3.11") },
    @{ Cmd = "python"; Args = @() }
)
$Py = $null
$PyArgs = @()
foreach ($c in $candidates) {
    if (Get-Command $c.Cmd -ErrorAction SilentlyContinue) {
        $v = Get-PyVersion $c.Cmd $c.Args
        if ($v -eq "3.12" -or $v -eq "3.11") { $Py = $c.Cmd; $PyArgs = $c.Args; break }
    }
}
if (-not $Py) {
    Write-Host "Polarity needs Python 3.12 (3.11 also works; 3.13+ is not supported yet)." -ForegroundColor Yellow
    Write-Host "  Install:  winget install Python.Python.3.12"
    Write-Host "  or download from https://www.python.org/downloads/windows/ (tick 'Add python.exe to PATH')."
    exit 1
}
Write-Host "Using $Py $($PyArgs -join ' ') (Python $(Get-PyVersion $Py $PyArgs))"

$Venv = Join-Path $Root ".venv"
$VenvPy = Join-Path $Venv "Scripts\python.exe"
if (Test-Path -LiteralPath $VenvPy) {
    $have = Get-PyVersion $VenvPy @()
    if ($have -ne "3.12" -and $have -ne "3.11") {
        Write-Host "Existing .venv uses Python $have; recreating it."
        Remove-Item -LiteralPath $Venv -Recurse -Force
    }
}
if (-not (Test-Path -LiteralPath $VenvPy)) {
    Invoke-Checked $Py ($PyArgs + @("-m", "venv", $Venv))
}

Invoke-Checked $VenvPy @("-m", "pip", "install", "-U", "pip", "wheel")
Invoke-Checked $VenvPy @("-m", "pip", "install", "-r", "requirements.txt", "-r", "requirements-dev.txt")
Invoke-Checked $VenvPy @("-m", "pip", "install", "-e", ".")

$EnvFile = Join-Path $Root ".env"
if (-not (Test-Path -LiteralPath $EnvFile)) {
    Copy-Item -LiteralPath (Join-Path $Root ".env.example") -Destination $EnvFile
    $LocalEnv = Join-Path $Root ".env.local"
    if ((Test-Path -LiteralPath $LocalEnv) -and (Select-String -LiteralPath $LocalEnv -Pattern '^NEBIUS_API_KEY=.+' -Quiet)) {
        Write-Host "Created .env from .env.example. The key in .env.local is used (it overrides .env), so no need to edit .env."
    } else {
        Write-Host "Created .env from .env.example. Paste your NEBIUS_API_KEY into it."
    }
}

Write-Host "Rendering demo scenes (synthetic placeholders for demo mode)..."
& $VenvPy -m polarity render-synthetic | Out-Null

& $VenvPy -m polarity doctor
$code = $LASTEXITCODE
Write-Host ""
Write-Host "Next: scripts\verify_windows.bat (needs NEBIUS_API_KEY), then scripts\run_windows.bat"
exit $code
