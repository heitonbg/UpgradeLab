param(
    [Parameter(Mandatory=$true)][string]$Database,
    [Parameter(Mandatory=$true)][string]$Schema,
    [Parameter(Mandatory=$true)][string]$Inbox,
    [Parameter(Mandatory=$true)][string]$Plans
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$databasePath = (Resolve-Path -LiteralPath $Database).Path
$schemaPath = (Resolve-Path -LiteralPath $Schema).Path
$inboxPath = (Resolve-Path -LiteralPath $Inbox).Path
if (-not $databasePath.EndsWith('.analysis.db')) { throw 'Use a separate .analysis.db database.' }
$feedFile = Get-ChildItem -LiteralPath $inboxPath -File -Filter '*.xlsx' | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
if (-not $feedFile) { Write-Output 'No local workbook supplied; no changes.'; exit 0 }
$feedHash = (Get-FileHash -LiteralPath $feedFile.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
New-Item -ItemType Directory -Path $Plans -Force | Out-Null
$plansPath = (Resolve-Path -LiteralPath $Plans).Path
$planPath = Join-Path $plansPath ($feedHash + '.preview.json')
if (Test-Path -LiteralPath $planPath) { Write-Output 'Unchanged local workbook; existing preview retained. Regenerate manually if Hardware/schema changed.'; exit 0 }
Push-Location (Join-Path $projectRoot 'backend')
try {
    & '.\.venv\Scripts\python.exe' -m scripts.import_catalog --database $databasePath preview --file $feedFile.FullName --schema $schemaPath --plan $planPath
    if ($LASTEXITCODE -ne 0) { throw 'Preview failed; database unchanged.' }
} finally { Pop-Location }
# Deliberately no download, automatic apply, task registration, or public enablement.
