param(
    [switch]$Restart,
    [switch]$RestartOnly
)
$ErrorActionPreference = 'Stop'
$taskIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
if ($taskIdentity.Name -match '(?i)codex') { throw 'Run as your Windows user, not a Codex sandbox account.' }
$taskPrincipal = [Security.Principal.WindowsPrincipal]$taskIdentity
if ($RestartOnly) {
    if (-not $taskPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Windows administrator approval is required to restart RabbitMQ.'
    }
    Restart-Service -Name RabbitMQ -ErrorAction Stop
    (Get-Service -Name RabbitMQ).WaitForStatus('Running', [TimeSpan]::FromSeconds(45))
    exit 0
}
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot 'backend\.venv\Scripts\python.exe'
Push-Location -LiteralPath $taskRoot
try {
    & $taskPython -m scripts.prepare_rabbitmq_local
    if ($LASTEXITCODE -ne 0) { throw 'TLS preparation failed. Service configuration was not changed.' }
    $taskStage = Join-Path $taskRoot '.local\rabbitmq'
    $taskBase = Join-Path $env:APPDATA 'RabbitMQ'
    $taskService = Join-Path $taskBase 'document-platform'
    $taskConfig = Join-Path $taskBase 'rabbitmq.conf'
    if (-not (Test-Path -LiteralPath $taskBase -PathType Container)) { throw 'RabbitMQ service base was not found.' }
    if (Test-Path -LiteralPath $taskConfig) {
        $taskFirst = Get-Content -LiteralPath $taskConfig -TotalCount 1
        if ($taskFirst -ne '# document-platform local RabbitMQ TLS configuration') {
            throw 'An existing RabbitMQ configuration needs review; refusing to overwrite it.'
        }
    }
    if (-not (Test-Path -LiteralPath $taskService)) { New-Item -ItemType Directory -Path $taskService | Out-Null }
    if ((Get-Acl -LiteralPath $taskService).Owner -ne $taskIdentity.Name) {
        throw 'Unexpected service-folder owner; run under the original Windows user.'
    }
    $taskAclResult = & icacls.exe $taskService /inheritance:r /grant:r ($taskIdentity.Name + ':(OI)(CI)F') '*S-1-5-18:(OI)(CI)RX' '*S-1-5-32-544:(OI)(CI)F' 2>&1
    if ($LASTEXITCODE -ne 0) { throw 'Could not restrict the service-folder access rules.' }
    foreach ($taskName in @('ca.crt', 'server.crt', 'server.key', 'definitions.json')) {
        Copy-Item -LiteralPath (Join-Path $taskStage $taskName) -Destination (Join-Path $taskService $taskName)
        if ((Get-Acl -LiteralPath (Join-Path $taskService $taskName)).Owner -ne $taskIdentity.Name) {
            throw 'Unexpected file owner; stop and review the operator account.'
        }
    }
    if (Test-Path -LiteralPath $taskConfig) {
        $taskBackup = Join-Path $taskStage ('rabbitmq.conf.backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
        Copy-Item -LiteralPath $taskConfig -Destination $taskBackup
    }
    Copy-Item -LiteralPath (Join-Path $taskStage 'rabbitmq.conf') -Destination $taskConfig
    if ((Get-Acl -LiteralPath $taskConfig).Owner -ne $taskIdentity.Name) {
        throw 'Unexpected configuration owner; stop and review the operator account.'
    }
    Write-Output ('Installed local TLS configuration. File owner: ' + $taskIdentity.Name)
    if ($Restart) {
        if ($taskPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
            Restart-Service -Name RabbitMQ -ErrorAction Stop
            (Get-Service -Name RabbitMQ).WaitForStatus('Running', [TimeSpan]::FromSeconds(45))
        } else {
            Write-Output 'Windows will request administrator consent for the service restart.'
            $taskProcess = Start-Process -FilePath powershell.exe -Verb RunAs -WindowStyle Hidden -Wait -PassThru -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $PSCommandPath + '"'), '-RestartOnly')
            if ($taskProcess.ExitCode -ne 0) { throw 'The elevated service restart did not complete.' }
        }
    }
} finally { Pop-Location }
