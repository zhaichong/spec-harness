param(
    [Parameter(Mandatory = $true)][string]$SpecDir,
    [Parameter(Mandatory = $true)][ValidateSet('draft', 'delivery')][string]$Stage
)

$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot 'check_spec.py'

function Test-Python([string]$Exe, [string[]]$Prefix) {
    try {
        $output = & $Exe @($Prefix + @('-c', 'print(91)')) 2>$null
        return (($output | Out-String) -match '91')
    } catch {
        return $false
    }
}

$candidates = @(
    @{ Exe = 'py'; Prefix = @('-3') },
    @{ Exe = 'python'; Prefix = @() },
    @{ Exe = 'python3'; Prefix = @() }
)

foreach ($candidate in $candidates) {
    if (-not (Get-Command $candidate.Exe -ErrorAction SilentlyContinue)) { continue }
    if (-not (Test-Python $candidate.Exe $candidate.Prefix)) { continue }
    & $candidate.Exe @($candidate.Prefix + @($script, $SpecDir, '--stage', $Stage))
    exit $LASTEXITCODE
}

[Console]::Error.WriteLine('Spec check failed: Python not found. Install Python and ensure py, python, or python3 is on PATH.')
exit 1
