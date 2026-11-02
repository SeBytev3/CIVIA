<#
.SYNOPSIS
    Lanzador principal del orquestador autónomo de desarrollo y auditoría para CIVIA.
.DESCRIPTION
    Coordina automáticamente a Antigravity (agy CLI) como desarrollador y Codex (codex exec)
    como auditor independiente, con checkpoints en Git y verificación en Docker/PostgreSQL.
.PARAMETER Simulate
    Ejecuta el ciclo en modo de simulación determinista sin consumir APIs reales ni requerir CLIs externos.
.PARAMETER PreflightOnly
    Ejecuta únicamente el diagnóstico del entorno y las herramientas.
.PARAMETER Block
    Bloque objetivo de trabajo (ej. G2.1, G2.2, G3).
.PARAMETER Finding
    Hallazgo específico a remediar (ej. M-03, M-06).
.PARAMETER MaxCycles
    Número máximo de ciclos permitidos por hallazgo antes de detenerse.
.PARAMETER ResetState
    Reinicia el archivo de estado de memoria (orchestrator/state.json).
.EXAMPLE
    pwsh -File scripts/civia-autopilot.ps1
.EXAMPLE
    pwsh -File scripts/civia-autopilot.ps1 -Simulate
#>

[CmdletBinding()]
param (
    [switch]$Simulate,
    [switch]$PreflightOnly,
    [string]$Block,
    [string]$Finding,
    [int]$MaxCycles,
    [switch]$ResetState
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " CIVIA AUTOPILOT — ORQUESTADOR AUTÓNOMO DE DESARROLLO Y AUDITORÍA" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host ""

# Verificar si python está en el PATH
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "[ERROR] No se encontró 'python' en el PATH del sistema." -ForegroundColor Red
    Write-Host "Por favor instale Python 3.13 o 3.14 y asegúrese de agregarlo al PATH." -ForegroundColor Yellow
    exit 1
}

$repoRoot = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $repoRoot

$pythonArgs = @("-m", "orchestrator.main")

if ($Simulate) {
    $pythonArgs += "--simulate"
    Write-Host "[MODO] Activando modo SIMULACIÓN determinista." -ForegroundColor Yellow
}

if ($PreflightOnly) {
    $pythonArgs += "--preflight-only"
}

if ($Block) {
    $pythonArgs += @("--block", $Block)
}

if ($Finding) {
    $pythonArgs += @("--finding", $Finding)
}

if ($MaxCycles) {
    $pythonArgs += @("--max-cycles", $MaxCycles)
}

if ($ResetState) {
    $pythonArgs += "--reset"
}

try {
    # Ejecutar el controlador Python con UTF-8 y sin buffer para ver logs en vivo
    $env:PYTHONIOENCODING = "utf-8"
    $env:PYTHONUNBUFFERED = "1"
    & python -u @pythonArgs
    $exitCode = $LASTEXITCODE
} catch {
    Write-Host "[ERROR FATAL] Ocurrió una excepción durante la ejecución: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "[CIVIA-AUTOPILOT] Ejecución completada exitosamente." -ForegroundColor Green
} else {
    Write-Host "[CIVIA-AUTOPILOT] Proceso finalizado con código: $exitCode" -ForegroundColor Yellow
}
Write-Host ""
exit $exitCode
