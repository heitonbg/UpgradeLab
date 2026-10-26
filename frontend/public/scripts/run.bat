@echo off
setlocal
title UpgradeLab - Hardware report
set "UPGRADELAB_SCRIPT=%~f0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$content = Get-Content -LiteralPath $env:UPGRADELAB_SCRIPT -Raw; & ([scriptblock]::Create(($content -split ('#' + ' POWERSHELL'), 2)[1]))"
if errorlevel 1 echo Could not create the report. Please select your hardware manually.
pause
exit /b
# POWERSHELL
$ErrorActionPreference = 'Stop'
try {
    $cpus = @(Get-CimInstance Win32_Processor | ForEach-Object { @{ name = $_.Name.Trim(); cores = $_.NumberOfCores } })
    $gpus = @(Get-CimInstance Win32_VideoController | ForEach-Object { @{ name = $_.Name.Trim() } })
    $memoryModules = @(Get-CimInstance Win32_PhysicalMemory)
    $modules = @($memoryModules | ForEach-Object {
        $typeCode = if ($_.SMBIOSMemoryType) { [int]$_.SMBIOSMemoryType } else { [int]$_.MemoryType }
        $type = switch ($typeCode) { 24 { 'DDR3' } 26 { 'DDR4' } 34 { 'DDR5' } default { $null } }
        @{ capacity_gb = [math]::Round($_.Capacity / 1GB, 2); type = $type; speed_mhz = $_.ConfiguredClockSpeed }
    })
    $knownTypes = @($modules | ForEach-Object { $_.type } | Where-Object { $_ } | Select-Object -Unique)
    $memoryType = if ($knownTypes.Count -eq 1 -and @($modules | Where-Object { -not $_.type }).Count -eq 0) { $knownTypes[0] } else { $null }
    $report = @{
        version = 2
        cpus = $cpus
        gpus = $gpus
        memory = @{
            capacity_gb = [math]::Round(($memoryModules | Measure-Object Capacity -Sum).Sum / 1GB, 2)
            type = $memoryType
            channels = $null
            module_count = $modules.Count
            modules = $modules
        }
    }
    $json = $report | ConvertTo-Json -Depth 6
    $folder = Split-Path -Parent $env:UPGRADELAB_SCRIPT
    $outputPath = Join-Path $folder 'UpgradeLab-hardware.json'
    [System.IO.File]::WriteAllText($outputPath, $json, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host 'Report saved:' $outputPath
    Write-Host 'Return to UpgradeLab and upload the JSON file.'
    Write-Host 'Only hardware models and memory parameters are collected. No data is sent over the network.'
} catch {
    Write-Error $_
    exit 1
}
