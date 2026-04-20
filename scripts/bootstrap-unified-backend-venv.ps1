param(
    [string]$TargetVenv = "",
    [string]$SeedPython = "",
    [switch]$Recreate
)

$ErrorActionPreference = "Stop"

$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $TargetVenv) {
    $TargetVenv = Join-Path $workspaceRoot ".venv"
}

$targetVenvPath = [System.IO.Path]::GetFullPath($TargetVenv)
$seedCandidates = @()
if ($SeedPython) {
    $seedCandidates += $SeedPython
}
$seedCandidates += @(
    (Join-Path $workspaceRoot ".venv-module2-py311\Scripts\python.exe"),
    "python"
)

$resolvedSeedPython = $null
foreach ($candidate in $seedCandidates) {
    try {
        if ($candidate -eq "python") {
            $null = & python -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0) {
                $resolvedSeedPython = "python"
                break
            }
            continue
        }
        if (Test-Path $candidate) {
            $resolvedSeedPython = $candidate
            break
        }
    }
    catch {
        continue
    }
}

if (-not $resolvedSeedPython) {
    throw "No usable bootstrap Python was found. Expected .venv-module2-py311 or python on PATH."
}

$module2SeedPython = Join-Path $workspaceRoot ".venv-module2-py311\Scripts\python.exe"
if (-not (Test-Path $module2SeedPython)) {
    throw "Seed environment is missing: $module2SeedPython"
}

function Assert-ExitCode {
    param(
        [string]$StepName
    )

    if ($LASTEXITCODE -ne 0) {
        throw "$StepName failed with exit code $LASTEXITCODE"
    }
}

function Invoke-CheckedCommand {
    param(
        [string]$StepName,
        [string]$Executable,
        [string[]]$Arguments = @()
    )

    Write-Host "[bootstrap-unified-backend-venv] $StepName"
    & $Executable @Arguments
    Assert-ExitCode -StepName $StepName
}

function Invoke-RobocopyMirror {
    param(
        [string]$SourcePath,
        [string]$TargetPath
    )

    Write-Host "[bootstrap-unified-backend-venv] syncing site-packages from seed env"
    robocopy $SourcePath $TargetPath /E /NFL /NDL /NJH /NJS /NP | Out-Host
    if ($LASTEXITCODE -gt 7) {
        throw "robocopy failed with exit code $LASTEXITCODE"
    }
}

function Test-ImportSmoke {
    param(
        [string]$PythonExecutable
    )

    & $PythonExecutable -c "import fastapi, docx, openpyxl, graphrag, mineru, neo4j, pyarrow, sqlalchemy, psycopg, pytest, httpx; from mineru.model.table.rec.unet_table import utils_table_line_rec; print('unified_backend_venv_ready')"
    return ($LASTEXITCODE -eq 0)
}

function Assert-TopLevelRequirementsPresent {
    param(
        [string]$PythonExecutable,
        [string]$RepoRoot
    )

    $validationScript = @'
from pathlib import Path
from packaging.requirements import Requirement
from packaging.version import Version
import subprocess
import sys

repo = Path(sys.argv[1])
req_paths = [repo / "backend" / "requirements.txt", repo / "backend" / "requirements-dev.txt"]
freeze = subprocess.check_output([sys.executable, "-m", "pip", "freeze"], text=True, encoding="utf-8")
installed = {}
for raw in freeze.splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or " @ " in line or line.startswith("-e "):
        continue
    if "==" not in line:
        continue
    name, version = line.split("==", 1)
    installed[name.lower().replace("_", "-")] = version

missing = []
mismatch = []
for req_path in req_paths:
    for raw in req_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("-r "):
            continue
        req = Requirement(line)
        key = req.name.lower().replace("_", "-")
        installed_version = installed.get(key)
        if installed_version is None:
            missing.append(req.name)
            continue
        if req.specifier and Version(installed_version) not in req.specifier:
            mismatch.append(f"{req.name}={installed_version} !~ {req.specifier}")

print("top_level_missing=" + (", ".join(missing) if missing else "none"))
print("top_level_version_mismatch=" + (", ".join(mismatch) if mismatch else "none"))
raise SystemExit(1 if (missing or mismatch) else 0)
'@

    $validationScriptPath = Join-Path $env:TEMP "smart_doc_flow_validate_top_level_requirements.py"
    try {
        Set-Content -LiteralPath $validationScriptPath -Value $validationScript -Encoding utf8
        & $PythonExecutable $validationScriptPath $RepoRoot
        Assert-ExitCode -StepName "top-level dependency presence validation"
    }
    finally {
        if (Test-Path $validationScriptPath) {
            Remove-Item -LiteralPath $validationScriptPath -Force
        }
    }
}

Write-Host "[bootstrap-unified-backend-venv] workspace=$workspaceRoot"
Write-Host "[bootstrap-unified-backend-venv] target_venv=$targetVenvPath"
Write-Host "[bootstrap-unified-backend-venv] bootstrap_python=$resolvedSeedPython"
Write-Host "[bootstrap-unified-backend-venv] seed_python=$module2SeedPython"

$targetPython = Join-Path $targetVenvPath "Scripts\python.exe"
$seedSitePackages = Join-Path $workspaceRoot ".venv-module2-py311\Lib\site-packages"
$targetSitePackages = Join-Path $targetVenvPath "Lib\site-packages"

if ((-not $Recreate) -and (Test-Path $targetPython) -and (Test-ImportSmoke -PythonExecutable $targetPython)) {
    Assert-TopLevelRequirementsPresent -PythonExecutable $targetPython -RepoRoot $workspaceRoot
    Write-Host "[bootstrap-unified-backend-venv] existing target venv already passed smoke validation"
    Write-Host "[bootstrap-unified-backend-venv] completed"
    exit 0
}

if ($Recreate -and (Test-Path $targetVenvPath)) {
    Write-Host "[bootstrap-unified-backend-venv] recreating target venv"
    Remove-Item -LiteralPath $targetVenvPath -Recurse -Force
}

if (-not (Test-Path $targetVenvPath)) {
    Invoke-CheckedCommand `
        -StepName "creating target venv" `
        -Executable $resolvedSeedPython `
        -Arguments @("-m", "venv", $targetVenvPath)
}

if (-not (Test-Path $targetPython)) {
    throw "Unified venv Python was not created successfully: $targetPython"
}

Invoke-CheckedCommand `
    -StepName "upgrading pip toolchain" `
    -Executable $targetPython `
    -Arguments @("-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel")

if (-not (Test-Path $seedSitePackages)) {
    throw "Seed site-packages directory is missing: $seedSitePackages"
}

if (-not (Test-Path $targetSitePackages)) {
    throw "Target site-packages directory is missing: $targetSitePackages"
}

Invoke-RobocopyMirror -SourcePath $seedSitePackages -TargetPath $targetSitePackages

Invoke-CheckedCommand `
    -StepName "installing module3 database adapter" `
    -Executable $targetPython `
    -Arguments @("-m", "pip", "install", "psycopg[binary]")

Invoke-CheckedCommand `
    -StepName "aligning shared runtime overlays" `
    -Executable $targetPython `
    -Arguments @("-m", "pip", "install", "python-docx>=1.1.2", "httpx>=0.28.0", "pytest>=9.0.0")

if (-not (Test-ImportSmoke -PythonExecutable $targetPython)) {
    throw "Unified backend venv smoke validation failed after sync"
}

Assert-TopLevelRequirementsPresent -PythonExecutable $targetPython -RepoRoot $workspaceRoot

Write-Host "[bootstrap-unified-backend-venv] completed"
