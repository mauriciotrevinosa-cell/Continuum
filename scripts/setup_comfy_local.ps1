param(
    [Parameter(Mandatory = $true)][string]$CheckpointUrl,
    [Parameter(Mandatory = $true)][string]$CheckpointName,
    [Parameter(Mandatory = $true)][string]$CheckpointVersion,
    [Parameter(Mandatory = $true)][string]$CheckpointLicense,
    [Parameter(Mandatory = $true)][string]$CheckpointSource,
    [string]$IpAdapterModelUrl = "",
    [string]$IpAdapterModelName = "",
    [string]$ClipVisionUrl = "",
    [string]$ClipVisionName = "",
    [string]$InstallRoot = "C:\ContinuumData\tools\ComfyUI",
    [switch]$Start
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ComfyRepo = $InstallRoot
$Venv = Join-Path $ComfyRepo ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"

function Require-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found on PATH."
    }
}

function Download-IfMissing([string]$Url, [string]$Destination) {
    if (-not $Url) { return }
    if (Test-Path $Destination) {
        Write-Host "Already present: $Destination"
        return
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
    Write-Host "Downloading $Url"
    Invoke-WebRequest -Uri $Url -OutFile $Destination -UseBasicParsing
}

Require-Command git
Require-Command python

if (-not (Test-Path (Join-Path $ComfyRepo ".git"))) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ComfyRepo) | Out-Null
    git clone https://github.com/Comfy-Org/ComfyUI.git $ComfyRepo
} else {
    Write-Host "Using existing ComfyUI checkout at $ComfyRepo"
}

if (-not (Test-Path $Python)) {
    python -m venv $Venv
}

& $Python -m pip install --upgrade pip
& $Python -m pip install -r (Join-Path $ComfyRepo "requirements.txt")

$CustomNodes = Join-Path $ComfyRepo "custom_nodes"
$IpAdapterNode = Join-Path $CustomNodes "ComfyUI_IPAdapter_plus"
if (-not (Test-Path (Join-Path $IpAdapterNode ".git"))) {
    New-Item -ItemType Directory -Force -Path $CustomNodes | Out-Null
    git clone https://github.com/cubiq/ComfyUI_IPAdapter_plus.git $IpAdapterNode
}
$IpReq = Join-Path $IpAdapterNode "requirements.txt"
if (Test-Path $IpReq) {
    & $Python -m pip install -r $IpReq
}

$CheckpointPath = Join-Path (Join-Path $ComfyRepo "models\checkpoints") $CheckpointName
Download-IfMissing $CheckpointUrl $CheckpointPath

if ($IpAdapterModelUrl) {
    if (-not $IpAdapterModelName) { throw "-IpAdapterModelName is required with -IpAdapterModelUrl" }
    $IpPath = Join-Path (Join-Path $ComfyRepo "models\ipadapter") $IpAdapterModelName
    Download-IfMissing $IpAdapterModelUrl $IpPath
}
if ($ClipVisionUrl) {
    if (-not $ClipVisionName) { throw "-ClipVisionName is required with -ClipVisionUrl" }
    $ClipPath = Join-Path (Join-Path $ComfyRepo "models\clip_vision") $ClipVisionName
    Download-IfMissing $ClipVisionUrl $ClipPath
}

$Sha = (Get-FileHash -Algorithm SHA256 $CheckpointPath).Hash.ToLowerInvariant()
Write-Host "Checkpoint SHA-256: $Sha"

Push-Location $RepoRoot
try {
    uv run --no-sync python scripts/configure_comfy.py `
        --local-url "http://127.0.0.1:8188" `
        --checkpoint $CheckpointName `
        --version $CheckpointVersion `
        --sha256 $Sha `
        --license $CheckpointLicense `
        --source $CheckpointSource `
        --deny-source-excerpts
}
finally {
    Pop-Location
}

$Launch = "& `"$Python`" `"$(Join-Path $ComfyRepo 'main.py')`" --listen 127.0.0.1 --port 8188 --disable-api-nodes"
Write-Host ""
Write-Host "Local ComfyUI is installed/configured. Launch command:"
Write-Host $Launch
Write-Host "Then restart continuum-api and continuum-worker."

if ($Start) {
    Push-Location $ComfyRepo
    try {
        & $Python main.py --listen 127.0.0.1 --port 8188 --disable-api-nodes
    }
    finally {
        Pop-Location
    }
}
