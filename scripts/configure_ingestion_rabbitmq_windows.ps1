$ErrorActionPreference = 'Stop'
$intakeIdentity=[Security.Principal.WindowsIdentity]::GetCurrent()
if ($intakeIdentity.Name -match '(?i)codex') { throw 'Run with the real Windows operator account.' }
$intakeRoot=Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $intakeRoot
try {
    & .\backend\.venv\Scripts\python.exe -m scripts.prepare_ingestion_rabbitmq
    if ($LASTEXITCODE -ne 0) { throw 'Intake preparation failed.' }
    $intakeStage=Join-Path $intakeRoot '.local\rabbitmq\definitions.json'
    $intakeServiceDir=Join-Path $env:APPDATA 'RabbitMQ\document-platform'
    $intakeServiceFile=Join-Path $intakeServiceDir 'definitions.json'
    $intakeConfig=Join-Path $env:APPDATA 'RabbitMQ\rabbitmq.conf'
    if ((Get-Content -LiteralPath $intakeConfig -TotalCount 1) -ne '# document-platform local RabbitMQ TLS configuration') { throw 'Unrecognized broker configuration.' }
    foreach($intakePath in @($intakeStage,$intakeServiceDir,$intakeServiceFile)) {
        if ((Get-Acl -LiteralPath $intakePath).Owner -ne $intakeIdentity.Name) { throw 'Unexpected asset owner.' }
        if ((Get-Item -LiteralPath $intakePath).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Unsafe broker asset path.' }
    }
    $intakeCli=Join-Path ${env:ProgramFiles} 'RabbitMQ Server\rabbitmq_server-4.4.0\sbin\rabbitmqctl.bat'
    if (-not (Test-Path -LiteralPath $intakeCli -PathType Leaf)) { throw 'Installed RabbitMQ 4.4.0 CLI not found; set the verified installation path.' }
    Copy-Item -LiteralPath $intakeStage -Destination $intakeServiceFile
    $intakeCliOutput=& $intakeCli import_definitions $intakeServiceFile 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Output 'Local CLI authentication unavailable; applying staged definitions through the Windows service restart.'
        $intakeRestartScript=Join-Path $PSScriptRoot 'configure_rabbitmq_windows.ps1'
        $intakePrincipal=[Security.Principal.WindowsPrincipal]$intakeIdentity
        if ($intakePrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
            & $intakeRestartScript -RestartOnly
        } else {
            $intakeRestart=Start-Process powershell.exe -Verb RunAs -WindowStyle Hidden -Wait -PassThru -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$intakeRestartScript+'"'),'-RestartOnly')
            if($intakeRestart.ExitCode -ne 0){throw 'Broker restart did not complete; staged definitions preserved.'}
        }
    }
    Write-Output 'Approved intake permissions installed locally; queues and credentials preserved.'
} finally { Pop-Location }
