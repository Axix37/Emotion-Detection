# ============================================================
#  setup_scheduler.ps1
#  Registers a Windows Task Scheduler task that runs the
#  SQL -> Excel -> PowerPoint pipeline every Monday at 08:00 AM.
#
#  HOW TO RUN (once, as Administrator):
#    Right-click PowerShell -> "Run as administrator"
#    cd to the pipeline\ folder, then:
#    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#    .\setup_scheduler.ps1
#
#  To change the run time, edit $RunTime below and re-run.
#  To remove the task:
#    Unregister-ScheduledTask -TaskName "WeeklyReportPipeline" -Confirm:$false
# ============================================================

$TaskName  = "WeeklyReportPipeline"
$RunTime   = "08:00AM"   # 24-h also accepted, e.g. "08:00"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BatFile   = Join-Path $ScriptDir "run_pipeline.bat"

# Verify the batch file exists
if (-not (Test-Path $BatFile)) {
    Write-Error "Cannot find run_pipeline.bat at: $BatFile"
    exit 1
}

# Remove existing task with the same name (idempotent re-registration)
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed existing task '$TaskName'."
}

$Action   = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$BatFile`""

$Trigger  = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday `
    -At $RunTime

# Run with highest privileges, even if the user is not logged on
$Principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType S4U `
    -RunLevel Highest

$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -StartWhenAvailable `          # catches a missed run if PC was off on Monday
    -RunOnlyIfNetworkAvailable `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName  $TaskName `
    -Action    $Action `
    -Trigger   $Trigger `
    -Principal $Principal `
    -Settings  $Settings `
    -Force | Out-Null

Write-Host ""
Write-Host "Task '$TaskName' registered successfully." -ForegroundColor Green
Write-Host "  Runs   : Every Monday at $RunTime"
Write-Host "  Script : $BatFile"
Write-Host ""
Write-Host "To run it immediately for testing:"
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host ""
Write-Host "To view the log:"
Write-Host "  Get-Content '$ScriptDir\pipeline.log' -Tail 50"
