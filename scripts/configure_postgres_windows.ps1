param([switch]$InstallAndRestart)
$ErrorActionPreference='Stop'
# Load modules from this PowerShell installation when launched by PowerShell 7.
Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Management\Microsoft.PowerShell.Management.psd1')
Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1')
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
if($identity.Name -match '(?i)codex'){throw 'Run under your real Windows account.'}
$root=Split-Path -Parent $PSScriptRoot
$stage=Join-Path $root '.local\postgres'
$serviceDir=Join-Path $env:ProgramData 'DocumentPlatform\PostgreSQL'
$data='C:\Program Files\PostgreSQL\18\data'
if($InstallAndRestart){
    if(-not ([Security.Principal.WindowsPrincipal]$identity).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'Administrator consent required.'}
    $config=Join-Path $data 'postgresql.conf'
    $include="include_if_exists = '" + (Join-Path $serviceDir 'document-platform.conf').Replace('\','/') + "'"
    $current=[IO.File]::ReadAllText($config)
    if(-not $current.Contains($include)){[IO.File]::AppendAllText($config,[Environment]::NewLine+'# document-platform local TLS'+[Environment]::NewLine+$include+[Environment]::NewLine)}
    Restart-Service -Name postgresql-x64-18
    (Get-Service postgresql-x64-18).WaitForStatus('Running',[TimeSpan]::FromSeconds(45))
    exit 0
}
Push-Location -LiteralPath $root
try{
    & '.\backend\.venv\Scripts\python.exe' -m scripts.prepare_postgres_local
    if($LASTEXITCODE -ne 0){throw 'TLS preparation failed.'}
    if(-not(Test-Path -LiteralPath $serviceDir)){New-Item -ItemType Directory -Path $serviceDir -Force | Out-Null}
    if((Get-Acl -LiteralPath $serviceDir).Owner -ne $identity.Name){throw 'Unexpected TLS-directory owner.'}
    $permissions=& icacls.exe $serviceDir /inheritance:r /grant:r ($identity.Name+':(OI)(CI)F') '*S-1-5-20:(OI)(CI)RX' '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' 2>&1
    if($LASTEXITCODE -ne 0){throw 'Could not protect TLS directory.'}
    foreach($name in @('ca.crt','server.crt','server.key','pg_hba.conf','document-platform.conf')){Copy-Item -LiteralPath (Join-Path $stage $name) -Destination (Join-Path $serviceDir $name)}
    $backup=Join-Path $stage 'postgresql.conf.before-tls'
    if(-not(Test-Path -LiteralPath $backup)){Copy-Item -LiteralPath (Join-Path $data 'postgresql.conf') -Destination $backup}
    Write-Output 'TLS files prepared under the operator account; Windows will request consent for installation/restart.'
    $process=Start-Process powershell.exe -Verb RunAs -WindowStyle Hidden -Wait -PassThru -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$PSCommandPath+'"'),'-InstallAndRestart')
    if($process.ExitCode -ne 0){throw 'PostgreSQL TLS installation/restart did not complete.'}
}finally{Pop-Location}
