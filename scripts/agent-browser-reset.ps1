param(
  [string]$Session = "module4-ui-check",
  [string]$Url = "http://127.0.0.1:3000",
  [switch]$Open,
  [switch]$Wait,
  [switch]$Snapshot
)

$ErrorActionPreference = "Stop"

function Get-AgentBrowserHome {
  return Join-Path $env:USERPROFILE ".agent-browser"
}

function Test-AgentBrowserInstalled {
  $null = Get-Command agent-browser -ErrorAction Stop
}

function Remove-StaleAgentBrowserSessions {
  $agentBrowserHome = Get-AgentBrowserHome
  if (-not (Test-Path $agentBrowserHome)) {
    return @()
  }

  $removed = @()
  $pidFiles = Get-ChildItem -Path $agentBrowserHome -Filter "*.pid" -File -ErrorAction SilentlyContinue
  foreach ($pidFile in $pidFiles) {
    $sessionName = $pidFile.BaseName
    $pidRaw = (Get-Content $pidFile.FullName -ErrorAction SilentlyContinue | Select-Object -First 1)
    $pidValue = 0
    [void][int]::TryParse([string]$pidRaw, [ref]$pidValue)

    $processExists = $false
    if ($pidValue -gt 0) {
      $processExists = [bool](Get-Process -Id $pidValue -ErrorAction SilentlyContinue)
    }

    if ($processExists) {
      continue
    }

    Remove-Item $pidFile.FullName -Force -ErrorAction SilentlyContinue
    $portFile = Join-Path $pidFile.DirectoryName ($sessionName + ".port")
    if (Test-Path $portFile) {
      Remove-Item $portFile -Force -ErrorAction SilentlyContinue
    }
    $removed += $sessionName
  }

  return $removed
}

function Show-AgentBrowserStatus {
  $agentBrowserHome = Get-AgentBrowserHome
  Write-Host "[agent-browser] home: $agentBrowserHome"
  if (-not (Test-Path $agentBrowserHome)) {
    Write-Host "[agent-browser] no local state directory yet"
    return
  }

  $pidFiles = Get-ChildItem -Path $agentBrowserHome -Filter "*.pid" -File -ErrorAction SilentlyContinue
  if (-not $pidFiles) {
    Write-Host "[agent-browser] no active session pid files"
    return
  }

  $rows = foreach ($pidFile in $pidFiles) {
    $sessionName = $pidFile.BaseName
    $pidRaw = (Get-Content $pidFile.FullName -ErrorAction SilentlyContinue | Select-Object -First 1)
    $portFile = Join-Path $pidFile.DirectoryName ($sessionName + ".port")
    $portRaw = ""
    if (Test-Path $portFile) {
      $portRaw = (Get-Content $portFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    }
    $proc = $null
    if ($pidRaw) {
      $proc = Get-Process -Id ([int]$pidRaw) -ErrorAction SilentlyContinue
    }
    [PSCustomObject]@{
      Session = $sessionName
      Pid = $pidRaw
      Port = $portRaw
      ProcessExists = [bool]$proc
    }
  }

  $rows | Format-Table -AutoSize
}

Test-AgentBrowserInstalled

$removedSessions = Remove-StaleAgentBrowserSessions
if ($removedSessions.Count -gt 0) {
  Write-Host "[agent-browser] removed stale sessions: $($removedSessions -join ', ')"
} else {
  Write-Host "[agent-browser] no stale sessions found"
}

Show-AgentBrowserStatus

if ($Open) {
  Write-Host "[agent-browser] opening $Url with session '$Session'"
  & agent-browser --session $Session open $Url
}

if ($Wait) {
  Write-Host "[agent-browser] waiting for network idle on session '$Session'"
  & agent-browser --session $Session wait --load networkidle
}

if ($Snapshot) {
  Write-Host "[agent-browser] snapshot for session '$Session'"
  & agent-browser --session $Session snapshot -i
}
